
import psycopg2
import json
from datetime import datetime
import anthropic
import os
from dotenv import load_dotenv
import numpy as np
import openai

# Load environment variables
load_dotenv()

# Initialize Claude client
client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

# Initialize OpenAI client (for embeddings)
openai_client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Cache for embeddings to avoid regenerating them
embedding_cache = {}

def execute_sql(query, dbname="chatbot_semantic_db", user="cooperpenniman", 
                password="", host="localhost", port="5432"):
    """
    Connects to the PostgreSQL database and executes the given query.
    If the query is a SELECT, fetches and returns the results.
    For other queries, commits the changes.
    """
    try:
        # Connect to PostgreSQL (quietly)
        conn = psycopg2.connect(
            dbname=dbname,
            user=user,
            password=password,
            host=host,
            port=port
        )
        
        cur = conn.cursor()
        
        # Execute the query (silently)
        cur.execute(query)
        
        # If it's a SELECT statement, fetch results
        if query.strip().lower().startswith("select"):
            results = cur.fetchall()
            # Get column names
            colnames = [desc[0] for desc in cur.description]
            # Convert to list of dictionaries
            results = [dict(zip(colnames, row)) for row in results]
            # Only print result count for SELECT queries
            if len(results) > 0:
                print(f"Found {len(results)} results")
        else:
            results = []
        
        # Commit if needed and close the connection
        conn.commit()
        cur.close()
        conn.close()
        
        return results
    except Exception as e:
        # On error, print the query for debugging
        print(f"\nQuery that caused error: {query}")
        print(f"Database error: {str(e)}")
        return {"error": str(e)}

# Custom JSON encoder to handle datetime objects
class DateTimeEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, datetime):
            return obj.isoformat()
        return super().default(obj)

def get_embedding(text, model="text-embedding-3-small"):
    """
    Get embedding from OpenAI API using the specified model.
    Uses a cache to avoid regenerating embeddings for identical text.
    """
    # Check cache first
    cache_key = f"{text}_{model}"
    if cache_key in embedding_cache:
        return embedding_cache[cache_key]
    
    try:
        text = text.replace("\\n", " ")  # OpenAI recommends replacing newlines
        response = openai_client.embeddings.create(input=[text], model=model)
        embedding = response.data[0].embedding
        
        # Cache the result - silently
        embedding_cache[cache_key] = embedding
        return embedding
    except Exception as e:
        print(f"Error generating OpenAI embedding: {str(e)}")
        raise  # Re-raise the exception to be caught by the calling function

def generate_sql_from_nl(question, schema_description):
    """
    Uses a separate Claude instance to generate SQL from natural language and schema
    """
    try:
        print("\n🤖 Using Claude to generate SQL from natural language...")
        sql_generation_system_prompt = f"""You are an expert SQL query generator.
You will be given a natural language question and database schema information.
Your task is to generate the most appropriate SQL query to answer the question.

When writing SQL:
- Use proper JOINs when referencing multiple tables
- Include relevant WHERE clauses to filter data appropriately
- Use aggregation functions (COUNT, SUM, AVG, etc.) when needed
- Ensure the query is syntactically correct
- Only reference tables and columns that exist in the provided schema

ONLY return the SQL query without any explanation or additional text."""

        sql_generation_message = f"""
Database Schema:
{schema_description}

Question: {question}

Please generate the SQL query to answer this question:"""

        # Create a separate Claude message for SQL generation
        sql_response = client.messages.create(
            model="claude-3-opus-20240229",
            max_tokens=1000,
            temperature=0.0,  # Use low temperature for deterministic SQL
            system=sql_generation_system_prompt,
            messages=[
                {"role": "user", "content": sql_generation_message}
            ]
        )
        
        # Extract the SQL query from Claude's response
        sql_query = ""
        if sql_response.content:
            for content in sql_response.content:
                if content.type == 'text':
                    sql_query += content.text.strip()
        
        # Clean up any markdown code block markers
        sql_query = sql_query.replace("```sql", "").replace("```", "").strip()
        
        print(f"✅ Generated SQL: {sql_query}")
        return sql_query
        
    except Exception as e:
        print(f"Error generating SQL with Claude: {str(e)}")
        return f"Error: {str(e)}"

def get_schema_metadata(question):
    """
    Gets relevant schema metadata based on the user's question using vector similarity
    Returns the most semantically similar columns and their tables
    """
    # Get embedding for search query
    print(f"\n🔍 Searching for schema metadata relevant to: '{question}'")
    
    try:
        # Convert question to search terms
        search_terms = ' & '.join(word for word in question.lower().split() if len(word) >= 3)
        query_embedding = get_embedding(search_terms)
        print(f"✅ Generated search embedding with {len(query_embedding)} dimensions")
    except Exception as e:
        print(f"❌ Error generating embedding: {str(e)}")
        return []
    
    # This query will get the most similar columns
    query = """
    SELECT 
        object_type,
        table_name,
        column_name,
        description,
        similarity
    FROM (
        SELECT 
            'column' as object_type,
            table_name,
            column_name,
            column_description as description,
            1 - (embedding <=> array{query_embedding}::vector) as similarity
        FROM column_metadata
        UNION ALL
        SELECT 
            'table' as object_type,
            table_name,
            NULL as column_name,
            table_description as description,
            1 - (embedding <=> array{query_embedding}::vector) as similarity
        FROM table_metadata
    ) as combined
    ORDER BY similarity DESC
    LIMIT 15;
    """.replace("{query_embedding}", str(query_embedding))
    
    print("Executing vector similarity search...")
    results = execute_sql(query)
    
    # Format the metadata into a schema description
    schema_desc = []
    current_table = None
    tables_seen = set()
    
    for item in results:
        if item['object_type'] == 'table':
            if item['table_name'] not in tables_seen:
                schema_desc.append(f"\n--- {item['table_name']} table ---")
                if item['description']:
                    schema_desc.append(f"Description: {item['description']}")
                tables_seen.add(item['table_name'])
                current_table = item['table_name']
        else:  # column
            if current_table != item['table_name']:
                if item['table_name'] not in tables_seen:
                    schema_desc.append(f"\n--- {item['table_name']} table ---")
                    tables_seen.add(item['table_name'])
                current_table = item['table_name']
            desc = f"* {item['column_name']}"
            if item['description']:
                desc += f": {item['description']}"
            schema_desc.append(desc)
    
    return "\n".join(schema_desc)

def get_initial_response_from_claude(question):
    """
    Gets response from Claude using the Tools API for SQL generation.
    The tool handles most of the NL2SQL work when invoked.
    """
    # Define the SQL generation tool
    tools = [
        {
            "name": "generate_sql",
            "description": """
Generate SQL queries for questions about customer data, sales records, or database information.
This tool should ONLY be used when the user is asking about data stored in a database, 
such as customer information, order history, support tickets, or analytics.
DO NOT use this tool for questions about product specifications, features, pricing, or comparisons.

The tool will:
1. Search for relevant database schema information
2. Generate appropriate SQL based on the user's question
3. Execute the SQL query
4. Return both the SQL and the results

Simply pass the user's natural language question to this tool.
            """,
            "input_schema": {
                "type": "object",
                "properties": {
                    "question": {
                        "type": "string",
                        "description": "The user's natural language question about database information"
                    }
                },
                "required": ["question"]
            }
        }
    ]

    system_prompt = """You are a friendly and helpful AI assistant for TechCorp, specializing in both product information and database querying.

You have information about TechCorp's product catalog:

PREMIUM LAPTOPS:
- TechPro X1 ($1,299): 14" 4K OLED, Intel i7, 16GB RAM, 1TB SSD, NVIDIA RTX 3060
- UltraBook Pro ($1,599): 15.6" QHD 165Hz, AMD Ryzen 9, 32GB RAM, 2TB SSD, NVIDIA RTX 3070

BUDGET LAPTOPS:
- EcoBook ($699): 13.3" FHD IPS, Intel i5, 8GB RAM, 512GB SSD, Intel Iris Xe Graphics

SOFTWARE:
- TechGuard Pro ($129/year): Antivirus, VPN, password manager, 50GB backup
- ProductivitySuite ($9.99/month): Office suite with 2TB cloud storage

WARRANTY OPTIONS:
- Basic (Free): 1-year hardware warranty, 90-day phone support
- Premium ($199): 3-year extended warranty with accidental damage protection

WHEN TO USE THE SQL GENERATION TOOL:
Only use the generate_sql tool when the user is asking about:
- Customer data or customer information
- Sales data, order history, or purchase records
- Support tickets or customer service records
- Performance metrics, analytics, or reports that require database information

If the user is asking about product information, features, specifications, pricing, or comparisons, do NOT use the SQL tool. Instead, respond directly with your product knowledge."""

    # Send the request to Claude with tools enabled
    try:
        print("\n🔄 Sending request to Claude...")
        
        message = client.messages.create(
            model="claude-3-opus-20240229",
            max_tokens=1000,
            temperature=0.7,
            system=system_prompt,
            messages=[
                {"role": "user", "content": question}
            ],
            tools=tools
        )
        
        # Check if Claude used a tool
        tool_used = False
        if message.content and len(message.content) > 0:
            for content in message.content:
                if content.type == 'tool_use':
                    tool_used = True
                    print("✅ SQL generation tool was successfully invoked.")
                    
                    # Get the tool parameters
                    tool_name = content.name
                    tool_input = content.input
                    
                    if tool_name == "generate_sql":
                        # Get the natural language question from the tool input
                        nl_question = tool_input.get("question", question)
                        
                        # Process the SQL tool request
                        tool_result = process_sql_tool_request(nl_question)
                        
                        # Check if there was an error
                        if "error" in tool_result:
                            error_message = tool_result["error"]
                            return f"I tried to query the database, but encountered an error: {error_message}"
                        
                        # Format the result into a response with tags
                        sql_query = tool_result.get("sql_query", "")
                        return f"<sql_query>{sql_query}</sql_query><sql_results>{json.dumps(tool_result.get('results', []), cls=DateTimeEncoder)}</sql_results>"
        
        # If Claude didn't use the tool, return the text content
        response_text = ""
        if message.content:
            for content in message.content:
                if content.type == 'text':
                    response_text += content.text.strip()
                
        if response_text:
            return response_text
        else:
            # Fallback if no text content
            return "I couldn't generate a proper response. Please try rephrasing your question."
        
    except Exception as e:
        print(f"Error calling Claude API: {str(e)}")
        return f"Error generating response: {str(e)}"

def process_sql_tool_request(question):
    """
    Process the SQL tool request:
    1. Get schema metadata based on the question
    2. Generate SQL using a separate Claude instance
    3. Execute the SQL
    4. Return the results
    """
    try:
        # Get relevant schema based on the question
        schema_description = get_schema_metadata(question)
        
        if not schema_description:
            return {
                "error": "Could not retrieve database schema information."
            }
        
        # Generate SQL using Claude
        sql_query = generate_sql_from_nl(question, schema_description)
        
        if sql_query.startswith("Error:"):
            return {
                "error": sql_query
            }
        
        # Execute the SQL query
        print(f"\n⚙️ Executing SQL: {sql_query}")
        results = execute_sql(sql_query)
        
        # Return the results and the SQL query
        return {
            "sql_query": sql_query,
            "results": results,
            "schema_used": schema_description
        }
    except Exception as e:
        print(f"Error in process_sql_tool_request: {str(e)}")
        return {
            "error": str(e)
        }

def extract_sql_results(response):
    """
    Extracts SQL query and results from response if they exist.
    """
    result = {}
    
    if "<sql_query>" in response and "</sql_query>" in response:
        start = response.find("<sql_query>") + 11
        end = response.find("</sql_query>")
        result["query"] = response[start:end].strip()
    
    if "<sql_results>" in response and "</sql_results>" in response:
        start = response.find("<sql_results>") + 13
        end = response.find("</sql_results>")
        result["results"] = json.loads(response[start:end].strip())
    
    return result

def format_sql_results(query_results):
    """
    Formats SQL results for display
    """
    if isinstance(query_results, list):
        if not query_results:
            return "The query returned no results."
        
        # Format the results
        formatted = json.dumps(query_results, indent=2, cls=DateTimeEncoder)
        result_count = len(query_results)
        return f"Found {result_count} result{'s' if result_count != 1 else ''}:\n{formatted}"
    
    # If it's not a list, just return it as JSON
    return json.dumps(query_results, indent=2, cls=DateTimeEncoder)

def main():
    print("\nWelcome to TechCorp Assistant! I can help you with:")
    print("1. Customer and sales data analysis")
    print("2. Product information and specifications")
    print("Just let me know what you'd like to know about our products or customer data!")
    
    while True:
        # Get user's input
        user_input = input("\nWhat would you like to know? (or 'quit' to exit): ")
        if user_input.lower() == 'quit':
            print("\nThank you for using TechCorp Assistant. Have a great day!")
            break
        
        try:
            print("\nProcessing your request...")
            
            # Get response from Claude
            initial_response = get_initial_response_from_claude(user_input)
            
            # Extract SQL query and results if present
            sql_data = extract_sql_results(initial_response)
            
            if sql_data:
                # Display the SQL that was generated
                if "query" in sql_data:
                    print("\n🔍 SQL Query:")
                    print(sql_data["query"])
                
                # Display the results
                if "results" in sql_data:
                    print("\n📊 Results:")
                    print(format_sql_results(sql_data["results"]))
            else:
                # For regular conversation or non-database questions
                print("\n" + initial_response)
            
        except Exception as e:
            print(f"Oops! Something went wrong: {str(e)}")
            print(f"Error details: {str(e)}")

if __name__ == "__main__":
    main()
