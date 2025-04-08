# TechCorp Assistant

This script provides an intelligent assistant for TechCorp that can answer questions about product information and query a database for customer/sales analytics.

## How It Works

The TechCorp Assistant uses Claude 3 Opus from Anthropic to create a conversational interface that can:

1. Answer questions about TechCorp's product catalog directly
2. Generate and execute SQL queries for database-related questions

### Architecture Overview

The assistant uses a hybrid approach for handling user queries:

- **For product questions**: The base Claude model responds directly using product information in its system prompt
- **For database questions**: The system uses a tool-based workflow to generate and execute SQL queries

### Key Components

#### 1. Base Claude Model Interface
- Determines if a user's question is about products or requires database access
- If it's about products, responds directly with product information
- If it requires database access, calls the SQL generation tool

#### 2. SQL Generation Tool
When invoked, the tool performs a complete workflow:
- Uses vector search to find relevant database schema (tables and columns)
- Employs a second Claude instance to generate SQL based on the question and schema
- Executes the SQL query against the PostgreSQL database
- Returns both the SQL query and results

#### 3. Vector Similarity Search
- Uses text embeddings from OpenAI's embedding model
- Performs vector similarity search against stored table/column descriptions
- Finds the database schema most relevant to the user's question

### Data Flow

1. User asks a question
2. Base Claude model determines if it's product-related or database-related
3. For product questions:
   - Claude responds directly with product information
   - No database interaction occurs
4. For database questions:
   - The SQL generation tool is invoked
   - Vector search finds relevant schema
   - A second Claude instance generates SQL
   - The SQL is executed and results are returned
   - Both SQL and results are displayed to the user

### Environment and Dependencies

- Python 3.6+
- PostgreSQL database with pgvector extension
- Required Python packages:
  - psycopg2-binary
  - anthropic
  - python-dotenv
  - numpy
  - openai

### Database Requirements

The system expects:
- A PostgreSQL database named 'chatbot_semantic_db'
- Tables named 'table_metadata' and 'column_metadata'
- Vector type columns for storing embeddings

## Setup Instructions

1. Create and activate a virtual environment
2. Install dependencies
3. Set up environment variables in a .env file
4. Ensure PostgreSQL server is running with pgvector extension
5. Run the script with `python3 tooltest.py`

## Key Features

- **Intelligent routing**: Determines whether to use product knowledge or database queries
- **Vector-based schema matching**: Uses semantic search to find relevant database schema
- **Natural language to SQL**: Converts questions into SQL using two-stage Claude processing
- **Clean separation of concerns**: Base model only decides routing; tool handles SQL generation

## Usage

Simply ask questions in natural language. For example:
- "Tell me about the TechPro X1 laptop" (product query)
- "What are the specs of the UltraBook Pro?" (product query)
- "How many customers signed up last month?" (database query)
- "Which products have the highest sales volume?" (database query)

The system will automatically determine how to best answer your question.



Setup and Execution Instructions:

1. Environment Setup:
   - Ensure Python 3.6+ is installed.
   - It is recommended to use a virtual environment to manage dependencies.
   - Navigate to the script's directory: cd /Users/cooperpenniman/Downloads/
   - Create a virtual environment: python3 -m venv venv
   - Activate the virtual environment: source venv/bin/activate

2. Install Dependencies:
   - With the virtual environment active, install required packages:
     pip install psycopg2-binary anthropic python-dotenv numpy openai

3. Environment Variables:
   - Create a file named `.env` in the same directory as the script (/Users/cooperpenniman/Downloads/).
   - Add your API keys to the `.env` file:
     ANTHROPIC_API_KEY=your_actual_anthropic_key
     OPENAI_API_KEY=your_actual_openai_key

4. Database Setup:
   - Ensure PostgreSQL server is running.
   - The script connects to a database named 'chatbot_semantic_db' by default.
   - Enable the pgvector extension in the database.
   - The script expects tables 'table_metadata' and 'column_metadata' with vector type columns for embeddings.

5. Running the Script:
   - Make sure your virtual environment is active (`source venv/bin/activate` from the Downloads directory).
   - Navigate to the script's directory (`/Users/cooperpenniman/Downloads/`).
   - Run the script using: python3 tooltest.py
