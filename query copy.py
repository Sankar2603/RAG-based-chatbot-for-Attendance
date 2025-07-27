examples = [
                {
                    "input": "Which category had the highest actual sales, and how does it compare to planned sales?",
                    "query": """SELECT category, actual_sales, planned_sales FROM sbu ORDER BY actual_sales DESC LIMIT 1"""
                },
                {
                    "input": "How many departments are there in total?",
                    "query": """SELECT COUNT(DISTINCT departments) AS total_departments FROM departments"""
                },
                {
                    "input": "Which category had the highest sales variance?",
                    "query": """SELECT category, sales_variance FROM sbu ORDER BY sales_variance DESC LIMIT 1"""
                },
                {
                    "input": "What is the sales growth percentage for each category?",
                    "query": """SELECT category, sales_growth FROM sbu ORDER BY sales_growth DESC"""
                },
                {
                    "input": "Which department underperformed in gross profit percentage?",
                    "query": """SELECT departments, category, actual_gross_profit_percentage, planned_gross_profit_percentage,
                    (actual_gross_profit_percentage - planned_gross_profit_percentage) AS gp_percentage_difference
                    FROM departments ORDER BY gp_percentage_difference ASC LIMIT 1"""
                },
                {
                    "input": "What is the GP mix variance impact across categories?",
                    "query": """SELECT category, gp_mix_variance, gross_profit_variance FROM sbu ORDER BY gp_mix_variance DESC"""
                },
                {
                    "input": "Which department had the most significant positive sales variance in each category?",
                    "query": """SELECT d.category, d.departments, d.sales_variance
                    FROM departments d
                    JOIN (SELECT category, MAX(sales_variance) AS max_sales_variance
                        FROM departments GROUP BY category) max_var
                    ON d.category = max_var.category AND d.sales_variance = max_var.max_sales_variance
                    ORDER BY d.category"""
                },
                {
                    "input": "Compare actual vs planned gross profit percentage across categories",
                    "query": """SELECT category, actual_gross_profit_percentage, planned_gross_profit_percentage
                    FROM sbu ORDER BY category"""
                },
                {
                    "input": "Which department had the highest actual gross profit?",
                    "query": """SELECT departments, actual_gross_profit FROM departments ORDER BY actual_gross_profit DESC LIMIT 1"""
                },
                {
                    "input": "Analyze the performance of the jewelry department",
                    "query": """SELECT * FROM departments WHERE departments ILIKE '%jewelry%'"""
                },
                {
                    "input": "Which departments had a gross profit percentage below their planned percentage, and by how much?",
                    "query": """SELECT departments, actual_gross_profit_percentage, planned_gross_profit_percentage, (actual_gross_profit_percentage - planned_gross_profit_percentage) AS percentage_difference FROM departments WHERE actual_gross_profit_percentage < planned_gross_profit_percentage ORDER BY percentage_difference ASC;"""
                },
                {
                    "input": "For the Electronics category, what are the actual and planned sales, and what is the sales growth percentage?",
                    "query": """SELECT departments, actual_sales, planned_sales, sales_growth FROM sbu WHERE sbu ILIKE '%Electronics%';"""
                },
                {
                    "input": "Which departments in the APPAREL & HOMELINES SBU had the highest actual revenue",
                    "query": """SELECT Department, Actual_Revenue_Mn, Actual_Gross_Profit, (Actual_Gross_Profit / Actual_Revenue_Mn * 100) AS gross_profit_margin FROM Upload_file_v1 WHERE Department IN ('Housewares', 'Appliances', 'Home Furniture', 'Household items', 'Curtains & Drapes', 'Bedding', 'Mens Wear', 'Boys Wear', 'Footwear', 'Infants & Toddlers', 'Hosiery', 'Lingerie', 'Foundations', 'Accessories', 'Jewelry', 'Girls Wear', 'Ladies Wear', 'Plus Size', 'Outerwear') ORDER BY Actual_Revenue_Mn DESC LIMIT 5;"""
                }
            ]
