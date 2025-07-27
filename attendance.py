from langchain_groq import ChatGroq
from langchain_community.utilities import SQLDatabase
from langchain_community.agent_toolkits import create_sql_agent
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from sqlalchemy import create_engine, text
import streamlit as st
import pandas as pd


DB_CONFIG = {
    "user": "root",
    "password": "Monkey26",
    "host": "ABCDEFGHSQL-v01.mssql.shr.prod.sin3.secureserver.net",
    "port": "1433",
    "database": "office",
    "driver": "ODBC Driver 17 for SQL Server"
}

GROQ_API_KEY = "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"

system_prefix = """You are an agent designed to interact with a SQL database.
You are a SQL assistant. Do not guess. Use the table schemas below to construct precise SQL queries. Do not output explanations unless asked. Return only concise answers.

IMPORTANT: The available tables are ONLY:
1. tblEmpDetails
2. tblAttendanceDetail

DO NOT try to access any other tables. Always use these exact table names.
Table structures:
tblempdetails:
- EmpID (varchar(256))
- Sno (int)
- FirstName (varchar(256))
- LastName (varchar(256))
- Company (varchar(256))
- Designation (nvarchar(256))
- EmailID (nvarchar(256))
- MobileNo (varchar(256))
- AddedBy (varchar(256))
- AddedDate (datetime)
- UpdatedBy (varchar(256))
- UpdatedDate (datetime)
- EmpLoginID (nvarchar(256))
- ProfilePic (nvarchar(max))
- NotificationGroup (varchar(256))
- DOB (date)
- DOJ (date)
- TokenID (nvarchar(max))
- TokenIDDateTime (datetime)
- OTP (varchar(256))
- OTPSentDate (datetime)
- Gender (varchar(256))
- UserProfilePic (nvarchar(256))
- AutogenerateID (int)
- Status (bit)

tblattendancedetail:
- Sno (int)
- EmpLoginID (varchar(200))
- AttendanceDate (date)
- InTime (nvarchar(200))
- OutTime (nvarchar(200))
- AttendanceStatus (varchar(200))
- AddedDate (date)
- AddedBy (varchar(200))
- WorkMode (varchar(200))
- PunchInStatus (bit)
- PunchOutStatus (bit)

Given an input question, create a syntactically correct query to run, then look at the results of the query and return the answer.
You can order the results by a relevant column to return the most interesting examples in the database.
Never query for all the columns from a specific table, only ask for the relevant columns given the question.
You have access to tools for interacting with the database.
Only use the given tools. Only use the information returned by the tools to construct your final answer.
You MUST double check your query before executing it. If you get an error while executing a query, rewrite the query and try again.
DO NOT make any DML statements (INSERT, UPDATE, DELETE, DROP etc.) to the database.
Try to fetch all relevant columns for the given questions so it can be useful to give more details in the end result.
Be a bit more eloquent in your response and try to give a detailed explanation of the results.
If the question does not seem related to the database, just return "I don't know" as the answer.
Only return 'Hey, How you doing! Any queries?' for exact inputs like 'hi', 'hello', or 'hey'. For all other prompts, assume they are database-related and generate a SQL query based on the provided schema and examples. If the prompt is vague (e.g., requesting data for unspecified employees), return 'Please specify employee names or IDs.' If no results are found, return 'No attendance records found for the specified employees today.'
To start you should ALWAYS look at the tables in the database to see what you can query.
For prompts requesting specific employee data (e.g., in-time for two employees), ensure the query uses precise identifiers like FirstName or EmpLoginID. If the prompt is vague, assume it refers to two employees and request clarification or use example names (e.g., 'John', 'Jane'). If no results are found, return 'No attendance records found for the specified employees today.' instead of 'I don't know.' Always return structured results or a clear message.

Do NOT skip this step.
Then you should query the schema of the most relevant tables.

Example prompt-queries:
1. 
Prompt: Who is absent today?  
Query:
SELECT e.FirstName, e.LastName, e.Designation
FROM tblEmpDetails e
WHERE e.EmpLoginID NOT IN (
  SELECT a.EmpLoginID
  FROM tblAttendanceDetail a
  WHERE a.AttendanceStatus= 'Present' AND a.AttendanceDate = CAST(GETDATE() AS DATE)
);

2. 
Prompt: List employees who are present today.  
Query:
SELECT e.FirstName, e.LastName 
FROM tblEmpDetails e 
JOIN tblAttendanceDetail a ON e.EmpLoginID = a.EmpLoginID 
WHERE a.AttendanceStatus='Present' AND a.AttendanceDate = CAST(GETDATE() AS DATE);

3. 
Prompt: Who entered office first today?  
Query:
SELECT CONCAT(e.FirstName, ' ', e.LastName) AS Name, a.InTime 
FROM tblEmpDetails e 
JOIN tblAttendanceDetail a ON e.EmpLoginID = a.EmpLoginID 
WHERE a.AttendanceStatus='Present' AND a.AttendanceDate = CAST(GETDATE() AS DATE)
ORDER BY a.InTime ASC 
OFFSET 0 ROWS FETCH NEXT 1 ROWS ONLY;

4. 
Prompt: Get list of employees who haven't punched out yet.  
Query:
SELECT e.FirstName, e.LastName 
FROM tblEmpDetails e 
JOIN tblAttendanceDetail a ON e.EmpLoginID = a.EmpLoginID 
WHERE a.AttendanceStatus='Present' AND a.PunchOutStatus = 0 AND a.AttendanceDate = CAST(GETDATE() AS DATE);

5. 
Prompt: How many employees are working from home today?  
Query:
SELECT COUNT(*) 
FROM tblAttendanceDetail 
WHERE AttendanceStatus='Present' AND WorkMode = 'Remote' AND AttendanceDate = CAST(GETDATE() AS DATE);

6. 
Prompt: Show today's attendance   
Query:
SELECT e.FirstName, e.LastName, a.AttendanceStatus
FROM tblEmpDetails e 
JOIN tblAttendanceDetail a ON e.EmpLoginID = a.EmpLoginID 
WHERE a.AttendanceDate = CAST(GETDATE() AS DATE)
ORDER BY AttendanceStatus;

7. 
Prompt: List all employees with their email and mobile number.  
Query:
SELECT FirstName, LastName, EmailID, MobileNo 
FROM tblEmpDetails;

8. 
Prompt: Find employees who joined after January 1, 2022.  
Query:
SELECT FirstName, LastName, DOJ 
FROM tblEmpDetails 
WHERE DOJ > '2022-01-01';

9.
Prompt: List all female employees.  
Query:
SELECT FirstName, LastName 
FROM tblEmpDetails 
WHERE Gender = 'Female';

10. 
Prompt: Find employees who came late today (after 9 AM).  
Query:
SELECT e.FirstName, e.LastName, a.InTime
FROM tblEmpDetails e
JOIN tblAttendanceDetail a ON e.EmpLoginID = a.EmpLoginID
WHERE a.AttendanceDate = CAST(GETDATE() AS DATE)
AND TRY_CAST(a.InTime AS TIME) > '09:00:00'
ORDER BY TRY_CAST(a.InTime AS TIME);

11.
Prompt: What is the in time of John Doe and Jane Smith 
Query: 
SELECT e.FirstName, e.LastName, a.InTime
FROM tblEmpDetails e
JOIN tblAttendanceDetail a ON e.EmpLoginID = a.EmpLoginID
WHERE a.AttendanceDate = CAST(GETDATE() AS DATE)
AND CONCAT(e.FirstName, ' ', e.LastName) IN ('John doe', 'Jane smith')
ORDER BY a.InTime;

"""

@st.cache_resource
def init_components():
    llm = ChatGroq(
        groq_api_key=GROQ_API_KEY,
        model_name="llama3-70b-8192",
        temperature=0,
        max_tokens=4000,
        max_retries=3,
        request_timeout=120
    )
    
    # MS SQL Server connection string
    connection_string = f"mssql+pyodbc://{DB_CONFIG['user']}:{DB_CONFIG['password']}@{DB_CONFIG['host']}:{DB_CONFIG['port']}/{DB_CONFIG['database']}?driver={DB_CONFIG['driver'].replace(' ', '+')}"
    
    db = SQLDatabase.from_uri(
        connection_string,
        sample_rows_in_table_info=3
    )
    
    agent = create_sql_agent(
        llm=llm,
        db=db,
        prefix=system_prefix,  
        verbose=True,
        agent_type="zero-shot-react-description",
        max_iterations=15,
        handle_parsing_errors=True,
        max_execution_time=120
    )
    
    return agent, db

st.set_page_config(page_title="HR Attendance Bot", layout="wide")
st.title("HR Attendance Assistant")

try:
    agent, db = init_components()
    
    with db._engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    st.success("Database connected")
    
except Exception as e:
    st.error(f"Connection failed: {str(e)}")
    st.stop()

if "messages" not in st.session_state:
    st.session_state.messages = []

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.write(message["content"])

if prompt := st.chat_input("Ask about attendance data..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.write(prompt)
    
    with st.chat_message("assistant"):
        with st.spinner("Querying database..."):
            try:
                response = agent.invoke({"input": prompt})
                answer = response["output"]
                
                answer = answer.replace("I'll help you", "").replace("Let me", "")
                answer = answer.strip()
                
                st.write(answer)
                st.session_state.messages.append({"role": "assistant", "content": answer})
                
            except Exception as e:
                error_msg = f"Error: {str(e)}"
                st.error(error_msg)
                st.session_state.messages.append({"role": "assistant", "content": error_msg})

with st.sidebar:
    st.header("Quick Queries")
    
    quick_queries = [
        "Show today's attendance",
        "Who came late today?",
        "Calculate working hours for today",
        "Who is absent today?",
        "Show work mode distribution",
        "Who hasn't punched out yet?",
        "Show this week's attendance summary",
        "Who worked overtime today?",
        "Show attendance by department",
        "What's today's attendance rate?"
    ]
    
    for query in quick_queries:
        if st.button(query, key=query):
            st.session_state.messages.append({"role": "user", "content": query})
            
            try:
                response = agent.invoke({"input": query})
                answer = response["output"].strip()
                st.session_state.messages.append({"role": "assistant", "content": answer})
                st.rerun()
            except Exception as e:
                st.session_state.messages.append({"role": "assistant", "content": f"Error: {str(e)}"})
                st.rerun()
    
    if st.button("Clear Chat"):
        st.session_state.messages = []
        st.rerun()