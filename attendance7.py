from langchain_groq import ChatGroq
from langchain_community.utilities import SQLDatabase
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from sqlalchemy import create_engine, text
import streamlit as st
import pandas as pd
from urllib.parse import quote_plus
import re
import random
from typing import TypedDict, List, Dict, Any, Optional
import json
from datetime import datetime, timedelta

# Try to import LangGraph components, fallback to simple implementation if not available
try:
    from langgraph.graph import StateGraph, START, END
    from langgraph.checkpoint.memory import MemorySaver
    LANGGRAPH_AVAILABLE = True
except ImportError:
    LANGGRAPH_AVAILABLE = False
    print("LangGraph not available, using simplified multi-agent approach")

# Database Configuration
DB_CONFIG = {
    "user": "dbAhhfficehr",
    "password": "plesk2024##",
    "host": "SG2NWPLS19SQL-v09.mssql.shr.prod.sin2.secureserver.net",
    "port": "1433",
    "database": "dbAhhfficehr",
    "driver": "ODBC Driver 17 for SQL Server"
}

GROQ_API_KEY = "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"

# State Definition for LangGraph
class AttendanceState(TypedDict):
    user_query: str
    query_type: str
    sql_query: str
    query_results: List[Dict]
    analysis: str
    final_response: str
    error: Optional[str]
    intermediate_steps: List[str]

# Agent Prompts
QUERY_CLASSIFIER_PROMPT = """
You are a query classification expert. Analyze the user's query and classify it into one of these categories:
- attendance_today: Questions about today's attendance
- attendance_summary: General attendance summaries
- employee_details: Questions about employee information
- late_early: Questions about late arrivals or early departures
- work_mode: Questions about work from home/office
- overtime: Questions about overtime or working hours
- absent_present: Questions about who is absent or present
- historical: Questions about past attendance data
- greeting: Simple greetings
- other: Any other type of query

User Query: {query}

Respond with just the category name and a brief explanation.
"""

SQL_GENERATOR_PROMPT = """
You are a SQL expert specializing in attendance and employee data. Generate the most efficient SQL query for the given request.

Available tables:
1. dbo.tblEmpDetails (employee information)
2. dbo.tblAttendanceDetail (attendance records)

Table schemas:
{table_schemas}

Query Type: {query_type}
User Query: {user_query}

Generate a precise SQL query. Return only the SQL query without explanations.
"""

RESPONSE_FORMATTER_PROMPT = """
You are a professional HR assistant. Format the query results into a clear, user-friendly response.

User Query: {user_query}
Query Results: {query_results}
Analysis: {analysis}

Create a professional, conversational response that directly answers the user's question.
Keep it concise but informative.
"""

# Greeting patterns and responses
GREETING_PATTERNS = [
    r'\b(hi|hello|hey|good morning|good afternoon|good evening|greetings|hiya|howdy)\b',
    r'\b(how are you|how do you do|what\'s up|whats up|sup)\b',
    r'\b(nice to meet you|pleased to meet you)\b'
]

GREETING_RESPONSES = [
    "Hello! I'm your Ahhfice Assistant. I can help you with attendance queries, employee information, and much more. What would you like to know?",
    "Hi there! I'm here to help you with all your attendance and employee data needs. Feel free to ask me anything!",
    "Hey! Welcome to Ahhfice Assistant. I can answer questions about attendance, employee details, and work patterns. How can I assist you today?"
]

# SQL Query Templates
QUERY_TEMPLATES = {
    "attendance_today": """
        SELECT e.FirstName, e.LastName, a.AttendanceStatus, a.InTime, a.OutTime, a.WorkMode
        FROM dbo.tblEmpDetails e 
        LEFT JOIN dbo.tblAttendanceDetail a ON e.EmpLoginID = a.EmpLoginID 
        WHERE a.AttendanceDate = CAST(GETDATE() AS DATE) OR a.AttendanceDate IS NULL
        ORDER BY a.AttendanceStatus, a.InTime
    """,
    "absent_today": """
        SELECT e.FirstName, e.LastName, e.Designation
        FROM dbo.tblEmpDetails e
        WHERE e.EmpLoginID NOT IN (
            SELECT a.EmpLoginID
            FROM dbo.tblAttendanceDetail a
            WHERE a.AttendanceStatus = 'Present' AND a.AttendanceDate = CAST(GETDATE() AS DATE)
        )
    """,
    "late_arrivals": """
        SELECT e.FirstName, e.LastName, a.InTime
        FROM dbo.tblEmpDetails e
        JOIN dbo.tblAttendanceDetail a ON e.EmpLoginID = a.EmpLoginID
        WHERE a.AttendanceDate = CAST(GETDATE() AS DATE)
        AND TRY_CAST(a.InTime AS TIME) > '09:00:00'
        ORDER BY TRY_CAST(a.InTime AS TIME) DESC
    """
}

class AttendanceBot:
    def __init__(self):
        self.llm = ChatGroq(
            groq_api_key=GROQ_API_KEY,
            model_name="llama3-70b-8192",
            temperature=0,
            max_tokens=4000,
            max_retries=5,
            request_timeout=240
        )
        self.db = self._init_database()
        
        if LANGGRAPH_AVAILABLE:
            self.memory = MemorySaver()
            self.graph = self._build_graph()
        else:
            self.memory = None
            self.graph = None
        
    def _init_database(self):
        """Initialize database connection"""
        odbc = (
            f"DRIVER={{ODBC Driver 17 for SQL Server}};"
            f"SERVER={DB_CONFIG['host']},{DB_CONFIG['port']};"
            f"DATABASE={DB_CONFIG['database']};"
            f"UID={DB_CONFIG['user']};"
            f"PWD={DB_CONFIG['password']};"
            f"TrustServerCertificate=yes;"
        )
        
        params = quote_plus(odbc)
        connection_string = f"mssql+pyodbc:///?odbc_connect={params}"
        
        return SQLDatabase.from_uri(
            connection_string,
            sample_rows_in_table_info=3,
            schema="dbo",
            include_tables=["tblEmpDetails", "tblAttendanceDetail"]
        )
    
    def _build_graph(self):
        """Build the LangGraph workflow"""
        if not LANGGRAPH_AVAILABLE:
            return None
            
        workflow = StateGraph(AttendanceState)
        
        # Add nodes
        workflow.add_node("query_classifier", self.classify_query)
        workflow.add_node("sql_generator", self.generate_sql)
        workflow.add_node("query_executor", self.execute_query)
        workflow.add_node("data_analyzer", self.analyze_data)
        workflow.add_node("response_formatter", self.format_response)
        workflow.add_node("greeting_handler", self.handle_greeting)
        
        # Add edges
        workflow.add_edge(START, "query_classifier")
        workflow.add_conditional_edges(
            "query_classifier",
            self.route_query,
            {
                "greeting": "greeting_handler",
                "sql_query": "sql_generator"
            }
        )
        workflow.add_edge("greeting_handler", END)
        workflow.add_edge("sql_generator", "query_executor")
        workflow.add_edge("query_executor", "data_analyzer")
        workflow.add_edge("data_analyzer", "response_formatter")
        workflow.add_edge("response_formatter", END)
        
        return workflow.compile(checkpointer=self.memory)
    
    def classify_query(self, state: AttendanceState) -> AttendanceState:
        """Agent 1: Classify the type of query"""
        prompt = ChatPromptTemplate.from_template(QUERY_CLASSIFIER_PROMPT)
        
        try:
            response = self.llm.invoke(
                prompt.format_messages(query=state["user_query"])
            )
            
            # Extract query type from response
            query_type = response.content.split()[0].lower()
            
            state["query_type"] = query_type
            state["intermediate_steps"] = [f"Classified query as: {query_type}"]
            
        except Exception as e:
            state["error"] = f"Classification error: {str(e)}"
            state["query_type"] = "other"
            
        return state
    
    def generate_sql(self, state: AttendanceState) -> AttendanceState:
        """Agent 2: Generate SQL query"""
        table_schemas = self.db.get_table_info()
        
        # Check if we have a template for this query type
        if state["query_type"] in QUERY_TEMPLATES:
            state["sql_query"] = QUERY_TEMPLATES[state["query_type"]]
        else:
            # Generate custom SQL using LLM
            prompt = ChatPromptTemplate.from_template(SQL_GENERATOR_PROMPT)
            
            try:
                response = self.llm.invoke(
                    prompt.format_messages(
                        table_schemas=table_schemas,
                        query_type=state["query_type"],
                        user_query=state["user_query"]
                    )
                )
                
                state["sql_query"] = response.content.strip()
                
            except Exception as e:
                state["error"] = f"SQL generation error: {str(e)}"
                state["sql_query"] = ""
        
        state["intermediate_steps"].append(f"Generated SQL: {state['sql_query']}")
        return state
    
    def execute_query(self, state: AttendanceState) -> AttendanceState:
        """Agent 3: Execute SQL query"""
        if state.get("error") or not state["sql_query"]:
            return state
            
        try:
            result = self.db.run(state["sql_query"])
            
            # Parse results into structured format
            if result:
                # Convert string result to list of dictionaries
                if isinstance(result, str):
                    # Simple parsing for basic results
                    lines = result.strip().split('\n')
                    if len(lines) > 1:
                        headers = lines[0].split('|') if '|' in lines[0] else [lines[0]]
                        data = []
                        for line in lines[1:]:
                            if line.strip():
                                values = line.split('|') if '|' in line else [line]
                                data.append(dict(zip(headers, values)))
                        state["query_results"] = data
                    else:
                        state["query_results"] = [{"result": result}]
                else:
                    state["query_results"] = result
            else:
                state["query_results"] = []
                
        except Exception as e:
            state["error"] = f"Query execution error: {str(e)}"
            state["query_results"] = []
            
        state["intermediate_steps"].append(f"Executed query, got {len(state['query_results'])} results")
        return state
    
    def analyze_data(self, state: AttendanceState) -> AttendanceState:
        """Agent 4: Analyze query results"""
        if state.get("error") or not state["query_results"]:
            state["analysis"] = "No data to analyze"
            return state
            
        try:
            results = state["query_results"]
            
            # Basic analysis based on query type
            if state["query_type"] == "attendance_today":
                present_count = sum(1 for r in results if r.get("AttendanceStatus") == "Present")
                total_count = len(results)
                state["analysis"] = f"Today's attendance: {present_count}/{total_count} employees present"
                
            elif state["query_type"] == "absent_today":
                state["analysis"] = f"{len(results)} employees are absent today"
                
            elif state["query_type"] == "late_arrivals":
                state["analysis"] = f"{len(results)} employees came late today"
                
            else:
                state["analysis"] = f"Found {len(results)} matching records"
                
        except Exception as e:
            state["analysis"] = f"Analysis error: {str(e)}"
            
        state["intermediate_steps"].append(f"Analysis: {state['analysis']}")
        return state
    
    def format_response(self, state: AttendanceState) -> AttendanceState:
        """Agent 5: Format final response"""
        if state.get("error"):
            state["final_response"] = "I encountered an error processing your request. Please try rephrasing your question."
            return state
            
        prompt = ChatPromptTemplate.from_template(RESPONSE_FORMATTER_PROMPT)
        
        try:
            response = self.llm.invoke(
                prompt.format_messages(
                    user_query=state["user_query"],
                    query_results=state["query_results"],
                    analysis=state["analysis"]
                )
            )
            
            state["final_response"] = response.content
            
        except Exception as e:
            # Fallback response
            if state["query_results"]:
                state["final_response"] = f"{state['analysis']}\n\nResults:\n"
                for i, result in enumerate(state["query_results"][:5]):  # Show first 5 results
                    state["final_response"] += f"{i+1}. {result}\n"
            else:
                state["final_response"] = "No results found for your query."
                
        return state
    
    def handle_greeting(self, state: AttendanceState) -> AttendanceState:
        """Handle greeting messages"""
        state["final_response"] = random.choice(GREETING_RESPONSES)
        return state
    
    def route_query(self, state: AttendanceState) -> str:
        """Route queries based on classification"""
        if state["query_type"] == "greeting":
            return "greeting"
        else:
            return "sql_query"
    
    def is_greeting(self, text: str) -> bool:
        """Check if input is a greeting"""
        text_lower = text.lower()
        for pattern in GREETING_PATTERNS:
            if re.search(pattern, text_lower):
                return True
        return False
    
    def process_query(self, query: str) -> str:
        """Process user query through the multi-agent system"""
        if self.is_greeting(query):
            return random.choice(GREETING_RESPONSES)
        
        # If LangGraph is available, use the graph workflow
        if LANGGRAPH_AVAILABLE and self.graph:
            initial_state = AttendanceState(
                user_query=query,
                query_type="",
                sql_query="",
                query_results=[],
                analysis="",
                final_response="",
                error=None,
                intermediate_steps=[]
            )
            
            try:
                # Run the graph
                config = {"configurable": {"thread_id": "main"}}
                result = self.graph.invoke(initial_state, config)
                return result["final_response"]
                
            except Exception as e:
                return f"I encountered an error: {str(e)}. Please try asking your question in a different way."
        
        # Fallback to sequential processing if LangGraph is not available
        else:
            return self._process_query_sequential(query)
    
    def _process_query_sequential(self, query: str) -> str:
        """Sequential processing when LangGraph is not available"""
        try:
            # Step 1: Classify query
            state = AttendanceState(
                user_query=query,
                query_type="",
                sql_query="",
                query_results=[],
                analysis="",
                final_response="",
                error=None,
                intermediate_steps=[]
            )
            
            # Step 2: Process through agents sequentially
            state = self.classify_query(state)
            if state["query_type"] == "greeting":
                return self.handle_greeting(state)["final_response"]
            
            state = self.generate_sql(state)
            if state.get("error"):
                return "I couldn't generate a proper SQL query for your request."
            
            state = self.execute_query(state)
            if state.get("error"):
                return "I encountered an error while executing the query."
            
            state = self.analyze_data(state)
            state = self.format_response(state)
            
            return state["final_response"]
            
        except Exception as e:
            return f"I encountered an error: {str(e)}. Please try asking your question in a different way."

# Streamlit UI
def main():
    st.set_page_config(page_title="Ahhfice Multi-Agent Assistant", layout="wide")
    st.title("🤖 Ahhfice Multi-Agent Assistant")
    st.markdown("*Powered by LangGraph with specialized agents for enhanced processing*")
    
    # Initialize bot
    @st.cache_resource
    def init_bot():
        return AttendanceBot()
    
    try:
        bot = init_bot()
        
        # Test database connection
        with bot.db._engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        st.success("✅ Database connected successfully")
        
    except Exception as e:
        st.error(f"❌ Connection failed: {str(e)}")
        st.stop()
    
    # Initialize chat history
    if "messages" not in st.session_state:
        st.session_state.messages = []
    
    # Display chat history
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.write(message["content"])
    
    # Chat input
    if prompt := st.chat_input("Ask about attendance data..."):
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.write(prompt)
        
        with st.chat_message("assistant"):
            with st.spinner("Processing through multi-agent system..."):
                response = bot.process_query(prompt)
                st.write(response)
                st.session_state.messages.append({"role": "assistant", "content": response})
    
    # Sidebar with agent information and quick queries
    with st.sidebar:
        st.header("🔧 Multi-Agent System")
        
        with st.expander("Agent Architecture"):
            if LANGGRAPH_AVAILABLE:
                st.write("""
                **🔄 LangGraph Multi-Agent System**
                
                **Agent 1: Query Classifier**
                - Analyzes and categorizes user queries
                
                **Agent 2: SQL Generator**
                - Creates optimized SQL queries
                
                **Agent 3: Query Executor**
                - Executes queries safely on database
                
                **Agent 4: Data Analyzer**
                - Analyzes results and extracts insights
                
                **Agent 5: Response Formatter**
                - Formats responses in natural language
                """)
            else:
                st.write("""
                **⚙️ Sequential Multi-Agent System**
                
                **Agent 1: Query Classifier**
                - Analyzes and categorizes user queries
                
                **Agent 2: SQL Generator**
                - Creates optimized SQL queries
                
                **Agent 3: Query Executor**
                - Executes queries safely on database
                
                **Agent 4: Data Analyzer**
                - Analyzes results and extracts insights
                
                **Agent 5: Response Formatter**
                - Formats responses in natural language
                
                *Note: Using sequential processing (LangGraph not available)*
                """)
            
        st.info("💡 Install LangGraph for enhanced workflow capabilities: `pip install langgraph`")
        
        st.header("📊 Quick Queries")
        
        quick_queries = [
            "Show today's attendance",
            "Who came late today?",
            "Who is absent today?",
            "Calculate working hours for today",
            "Show work mode distribution",
            "Who hasn't punched out yet?",
            "Show this week's attendance summary",
            "Who worked overtime today?",
            "Show attendance by department",
            "What's today's attendance rate?",
            "List all employees",
            "Show employees by designation"
        ]
        
        for query in quick_queries:
            if st.button(query, key=query):
                st.session_state.messages.append({"role": "user", "content": query})
                
                with st.spinner("Processing..."):
                    response = bot.process_query(query)
                    st.session_state.messages.append({"role": "assistant", "content": response})
                st.rerun()
        
        st.markdown("---")
        if st.button("🗑️ Clear Chat"):
            st.session_state.messages = []
            st.rerun()
        
        st.markdown("---")
        st.caption("Multi-agent system provides enhanced accuracy and processing capabilities.")

if __name__ == "__main__":
    main()