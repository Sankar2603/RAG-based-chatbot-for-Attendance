from langchain_groq import ChatGroq
from langchain_community.utilities import SQLDatabase
from langchain_community.agent_toolkits import create_sql_agent
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from sqlalchemy import create_engine, text
import streamlit as st
import pandas as pd
from urllib.parse import quote_plus
import re
import random

DB_CONFIG = {
    "user": "username",
    "password": "Password",
    "host": "Host",
    "port": "1433",
    "database": "database",
    "driver": "ODBC Driver 17 for SQL Server"
}

GROQ_API_KEY = "Your api key"

system_prefix = """
You are a SQL expert. Generate the most efficient, direct SQL query in as few steps as possible. Avoid unnecessary reasoning. 
You are an agent designed to interact with a SQL database.
You are a SQL assistant. Do not guess. Use the table schemas below to construct precise SQL queries. Do not output explanations unless asked. Return only concise answers.

IMPORTANT: The available tables are ONLY:
1. dbo.tblEmpDetails
2. dbo.tblAttendanceDetail

DO NOT try to access any other tables. Always use these exact table names.
Table structures:
dbo.tblempdetails:
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

dbo.tblattendancedetail:
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
Your task is to generate and execute SQL queries on the given database to retrieve accurate results. Do not explain the logic or Syntax. Simply return the output of the executed query as a table or list.You have to execute the query and send me the result alone.
If the question does not seem related to the database, just return "I don't know" as the answer.
To start you should ALWAYS look at the tables in the database to see what you can query.
For prompts requesting specific employee data (e.g., in-time for two employees), ensure the query uses precise identifiers like FirstName or EmpLoginID. If the prompt is vague, assume it refers to two employees and request clarification or use example names (e.g., 'John', 'Jane'). If no results are found, return 'No attendance records found for the specified employees today.' instead of 'I don't know.' Always return structured results or a clear message.

Do NOT skip this step.
Then you should query the schema of the most relevant tables.

Example prompt-queries:
1. 
Prompt: Who is absent today?  
Query:
SELECT e.FirstName, e.LastName, e.Designation
FROM dbo.tblEmpDetails e
WHERE e.EmpLoginID NOT IN (
  SELECT a.EmpLoginID
  FROM dbo.tblAttendanceDetail a
  WHERE a.AttendanceStatus= 'Present' AND a.AttendanceDate = CAST(GETDATE() AS DATE)
);

2. 
Prompt: List employees who are present today.  
Query:
SELECT e.FirstName, e.LastName 
FROM dbo.tblEmpDetails e 
JOIN dbo.tblAttendanceDetail a ON e.EmpLoginID = a.EmpLoginID 
WHERE a.AttendanceStatus='Present' AND a.AttendanceDate = CAST(GETDATE() AS DATE);

3. 
Prompt: Who entered office first today?  
Query:
SELECT CONCAT(e.FirstName, ' ', e.LastName) AS Name, a.InTime  
FROM dbo.tblEmpDetails e 
JOIN dbo.tblAttendanceDetail a ON e.EmpLoginID = a.EmpLoginID 
WHERE a.AttendanceStatus = 'Present' 
  AND a.AttendanceDate = CAST(GETDATE() AS DATE)
ORDER BY 
  TRY_CAST(a.InTime AS TIME) ASC
OFFSET 0 ROWS FETCH NEXT 1 ROWS ONLY;

4. 
Prompt: Get list of employees who haven't punched out yet.  
Query:
SELECT e.FirstName, e.LastName 
FROM dbo.tblEmpDetails e 
JOIN dbo.tblAttendanceDetail a ON e.EmpLoginID = a.EmpLoginID 
WHERE a.AttendanceStatus='Present' AND a.PunchOutStatus = 0 AND a.AttendanceDate = CAST(GETDATE() AS DATE);

5. 
Prompt: How many employees are working from home today?  
Query:
SELECT COUNT(*) 
FROM dbo.tblAttendanceDetail 
WHERE AttendanceStatus='Present' AND WorkMode = 'Remote' AND AttendanceDate = CAST(GETDATE() AS DATE);

6. 
Prompt: Show today's attendance   
Query:
SELECT e.FirstName, e.LastName, a.AttendanceStatus
FROM dbo.tblEmpDetails e 
JOIN dbo.tblAttendanceDetail a ON e.EmpLoginID = a.EmpLoginID 
WHERE a.AttendanceDate = CAST(GETDATE() AS DATE)
ORDER BY AttendanceStatus;

7. 
Prompt: List all employees with their email and mobile number.  
Query:
SELECT FirstName, LastName, EmailID, MobileNo 
FROM dbo.tblEmpDetails;

8. 
Prompt: Find employees who joined after January 1, 2022.  
Query:
SELECT FirstName, LastName, DOJ 
FROM dbo.tblEmpDetails 
WHERE DOJ > '2022-01-01';

9.
Prompt: List all female employees.  
Query:
SELECT FirstName, LastName 
FROM dbo.tblEmpDetails 
WHERE Gender = 'Female';

10. 
Prompt: Find employees who came late today (after 10 AM).  
Query:
SELECT e.FirstName, e.LastName, a.InTime
FROM dbo.tblEmpDetails e
JOIN dbo.tblAttendanceDetail a ON e.EmpLoginID = a.EmpLoginID
WHERE a.AttendanceDate = CAST(GETDATE() AS DATE)
AND TRY_CAST(a.InTime AS TIME) > '10:00:00'
ORDER BY TRY_CAST(a.InTime AS TIME);

11.
Prompt: Who worked the longest hours today?  
Query:
SELECT e.FirstName, e.LastName, 
       DATEDIFF(MINUTE, TRY_CAST(a.InTime AS TIME), TRY_CAST(a.OutTime AS TIME)) AS WorkingMinutes
FROM dbo.tblEmpDetails e
JOIN dbo.tblAttendanceDetail a ON e.EmpLoginID = a.EmpLoginID
WHERE a.AttendanceDate = CAST(GETDATE() AS DATE) AND a.OutTime IS NOT NULL
ORDER BY WorkingMinutes DESC
OFFSET 0 ROWS FETCH NEXT 1 ROWS ONLY;


12. 
Prompt: Show employees who have birthdays this month.  
Query:
SELECT FirstName, LastName, DOB
FROM dbo.tblEmpDetails
WHERE MONTH(DOB) = MONTH(GETDATE()) AND YEAR(DOB) IS NOT NULL
ORDER BY DAY(DOB);


13. 
Prompt: List employees who joined in the last 30 days.  
Query:
SELECT FirstName, LastName, DOJ, Company
FROM dbo.tblEmpDetails
WHERE DOJ >= DATEADD(DAY, -30, GETDATE())
ORDER BY DOJ DESC;

14. 
Prompt:Find employees who haven't punched in today.  
Query:
SELECT e.FirstName, e.LastName, e.Designation
FROM dbo.tblEmpDetails e
WHERE e.EmpLoginID NOT IN (
    SELECT a.EmpLoginID
    FROM dbo.tblAttendanceDetail a
    WHERE a.AttendanceDate = CAST(GETDATE() AS DATE) AND a.PunchInStatus = 1
);


15. 
Prompt: How many employees are present by company?  
Query:
SELECT e.Company, COUNT(*) as PresentCount
FROM dbo.tblEmpDetails e
JOIN dbo.tblAttendanceDetail a ON e.EmpLoginID = a.EmpLoginID
WHERE a.AttendanceStatus = 'Present' AND a.AttendanceDate = CAST(GETDATE() AS DATE)
GROUP BY e.Company;


16. 
Prompt: Show yesterday's attendance summary.  
Query:
SELECT AttendanceStatus, COUNT(*) as Count
FROM dbo.tblAttendanceDetail
WHERE AttendanceDate = CAST(DATEADD(DAY, -1, GETDATE()) AS DATE)
GROUP BY AttendanceStatus;


17. 
Prompt:List employees who left office earliest today.  
Query:
SELECT e.FirstName, e.LastName, a.OutTime
FROM dbo.tblEmpDetails e
JOIN dbo.tblAttendanceDetail a ON e.EmpLoginID = a.EmpLoginID
WHERE a.AttendanceDate = CAST(GETDATE() AS DATE) AND a.OutTime IS NOT NULL
ORDER BY TRY_CAST(a.OutTime AS TIME) ASC
OFFSET 0 ROWS FETCH NEXT 5 ROWS ONLY;


18. 
Prompt:Find all managers in the company.  
Query:
SELECT FirstName, LastName, Company, EmailID
FROM dbo.tblEmpDetails
WHERE Designation LIKE '%Manager%' OR Designation LIKE '%Lead%'
ORDER BY Company, FirstName;


19. 
Prompt:Show employees working from office today.  
Query:
SELECT e.FirstName, e.LastName, a.InTime
FROM dbo.tblEmpDetails e
JOIN dbo.tblAttendanceDetail a ON e.EmpLoginID = a.EmpLoginID
WHERE a.AttendanceDate = CAST(GETDATE() AS DATE) 
AND (a.WorkMode = 'Office' OR a.WorkMode = 'Onsite')
ORDER BY a.InTime;


20. 
Prompt: List employees who are currently active in the system.  
Query:
SELECT FirstName, LastName, Designation, Company
FROM dbo.tblEmpDetails
WHERE Status = 1
ORDER BY Company, FirstName;


21. 
Prompt: Find employees who had perfect attendance this week.  
Query:
SELECT e.FirstName, e.LastName, COUNT(*) as DaysPresent
FROM dbo.tblEmpDetails e
JOIN dbo.tblAttendanceDetail a ON e.EmpLoginID = a.EmpLoginID
WHERE a.AttendanceDate >= DATEADD(WEEK, DATEDIFF(WEEK, 0, GETDATE()), 0)
AND a.AttendanceStatus = 'Present'
GROUP BY e.FirstName, e.LastName, e.EmpLoginID
HAVING COUNT(*) = 5;


22. 
Prompt: Show employees who updated their profile recently.  
Query:
SELECT FirstName, LastName, UpdatedDate, UpdatedBy
FROM dbo.tblEmpDetails
WHERE UpdatedDate >= DATEADD(DAY, -7, GETDATE())
ORDER BY UpdatedDate DESC;


23. 
Prompt: List all male employees by designation.  
Query:
SELECT Designation, COUNT(*) as MaleCount
FROM dbo.tblEmpDetails
WHERE Gender = 'Male'
GROUP BY Designation
ORDER BY MaleCount DESC;

24. 
Prompt: Find employees who worked overtime today (after 6 PM).  
Query:
SELECT e.FirstName, e.LastName, a.OutTime
FROM dbo.tblEmpDetails e
JOIN dbo.tblAttendanceDetail a ON e.EmpLoginID = a.EmpLoginID
WHERE a.AttendanceDate = CAST(GETDATE() AS DATE)
AND TRY_CAST(a.OutTime AS TIME) > '18:00:00'
ORDER BY TRY_CAST(a.OutTime AS TIME) DESC;

25. 
Prompt: Show attendance pattern for last 5 days.  
Query:
SELECT AttendanceDate, AttendanceStatus, COUNT(*) as Count
FROM dbo.tblAttendanceDetail
WHERE AttendanceDate >= DATEADD(DAY, -5, GETDATE())
GROUP BY AttendanceDate, AttendanceStatus
ORDER BY AttendanceDate DESC, AttendanceStatus;

26. 
Prompt: List employees with no profile picture.  
Query:
SELECT FirstName, LastName, EmailID
FROM dbo.tblEmpDetails
WHERE ProfilePic IS NULL OR ProfilePic = '' OR UserProfilePic IS NULL OR UserProfilePic = ''
ORDER BY FirstName;

27. 
Prompt: Find employees who joined on the same day.  
Query:
SELECT DOJ, COUNT(*) as EmployeeCount, 
       STRING_AGG(CONCAT(FirstName, ' ', LastName), ', ') as Employees
FROM dbo.tblEmpDetails
WHERE DOJ IS NOT NULL
GROUP BY DOJ
HAVING COUNT(*) > 1
ORDER BY DOJ;

28. 
Prompt: Show employees who have been absent for more than 2 days this week.  
Query:
SELECT e.FirstName, e.LastName, COUNT(*) as AbsentDays
FROM dbo.tblEmpDetails e
JOIN dbo.tblAttendanceDetail a ON e.EmpLoginID = a.EmpLoginID
WHERE a.AttendanceDate >= DATEADD(WEEK, DATEDIFF(WEEK, 0, GETDATE()), 0)
AND a.AttendanceStatus = 'Absent'
GROUP BY e.FirstName, e.LastName
HAVING COUNT(*) > 2
ORDER BY AbsentDays DESC;

29. 
Prompt: List employees by their years of experience in the company.  
Query:
SELECT FirstName, LastName, DOJ, 
       DATEDIFF(YEAR, DOJ, GETDATE()) as YearsOfExperience
FROM dbo.tblEmpDetails
WHERE DOJ IS NOT NULL
ORDER BY YearsOfExperience DESC;

30. 
Prompt: Find employees who received OTP today.  
Query:
SELECT FirstName, LastName, OTP, OTPSentDate
FROM dbo.tblEmpDetails
WHERE CAST(OTPSentDate AS DATE) = CAST(GETDATE() AS DATE)
ORDER BY OTPSentDate DESC;

31.
Prompt: Who came late most of the times this month 
Query:
SELECT e.FirstName, e.LastName, COUNT(*) as LateCount
FROM dbo.tblEmpDetails e
JOIN dbo.tblAttendanceDetail a ON e.EmpLoginID = a.EmpLoginID
WHERE a.AttendanceDate >= DATEADD(DAY, -30, GETDATE())
AND TRY_CAST(a.InTime AS TIME) > '09:00:00'
GROUP BY e.FirstName, e.LastName
ORDER BY LateCount DESC;

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

def is_greeting(text):
    """Check if the input text is a greeting"""
    text_lower = text.lower()
    for pattern in GREETING_PATTERNS:
        if re.search(pattern, text_lower):
            return True
    return False

def get_random_response(responses):
    """Get a random response from the list"""
    return random.choice(responses)

def handle_user_input(prompt, agent):
    """Handle user input with appropriate responses"""
    
    # Check for greetings
    if is_greeting(prompt):
        return get_random_response(GREETING_RESPONSES)
    
    # For all other inputs, try to process with the agent
    try:
        response = agent.invoke({"input": prompt})
        answer = response["output"]
        
        # Clean up the response
        answer = answer.replace("I'll help you", "").replace("Let me", "")
        answer = answer.strip()
        
        return answer
        
    except Exception as e:
        return "I couldn't understand your request. Please ask a question related to attendance or employee data (e.g., 'Who is present today?', 'Show attendance summary', 'List all employees')."

@st.cache_resource
def init_components():
    llm = ChatGroq(
        groq_api_key=GROQ_API_KEY,
        model_name="llama3-70b-8192",
        temperature=0,
        max_tokens=4000,
        max_retries=5,
        request_timeout=240
    )
    
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

    db = SQLDatabase.from_uri(
        connection_string,
        sample_rows_in_table_info=3,
        schema="dbo",
        include_tables=["tblEmpDetails", "tblAttendanceDetail"]
    )
    
    agent = create_sql_agent(
        llm=llm,
        db=db,
        prefix=system_prefix,  
        verbose=True,
        agent_type="zero-shot-react-description",
        max_iterations=15,
        handle_parsing_errors=True,
        max_execution_time=240
    )
    
    return agent, db

# Streamlit UI
st.set_page_config(page_title="Ahhffice Attendance Bot", layout="wide")
st.title("Ahhfice Assistant")

try:
    agent, db = init_components()
    
    with db._engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    st.success("Database connected")
    
except Exception as e:
    st.error(f"Connection failed: {str(e)}")
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
        with st.spinner("Querying database..."):
            response = handle_user_input(prompt, agent)
            st.write(response)
            st.session_state.messages.append({"role": "assistant", "content": response})

# Sidebar with quick queries
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
            
            response = handle_user_input(query, agent)
            st.session_state.messages.append({"role": "assistant", "content": response})
            st.rerun()
    
    if st.button("Clear Chat"):
        st.session_state.messages = []
        st.rerun()
