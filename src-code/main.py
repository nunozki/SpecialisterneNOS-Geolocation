import csv
import requests
import logging
import sqlite3
import locale
import time
import pandas as pd
from concurrent.futures import ThreadPoolExecutor
from flask import Flask, jsonify

locale.setlocale(locale.LC_ALL, 'pt_PT.UTF-8')

# Configure logging at the beginning of your script
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s',
                    filename='app.log',  # Log to a file named 'app.log'
                    filemode='a')  # Append mode

# Function to read the CSV file
def read_csv(file_path):
    return pd.read_csv(file_path)

def handle_response(response, postal_code):
    if response.status_code == 200:
        data = response.json()
        if data and len(data) > 0:
            return data[0]['concelho'], data[0]['distrito']
    elif response.status_code in [400, 404]:
        logging.warning(f"Request error for postal code: {postal_code} - Status code: {response.status_code}")
    else:
        logging.error(f"Error fetching data for postal code: {postal_code} - Status code: {response.status_code}")
    return None, None

# Function to get municipality and district information
def get_municipality_and_district(postal_code, max_retries = 3):
    logging.info(f"Fetching data for postal code: {postal_code}")
    postal_code = postal_code.strip().replace(",", "").replace(" ", "").replace("-", "").zfill(7)

    if len(postal_code) < 7 or len(postal_code) > 8 or not postal_code.isdigit():
        logging.warning(f"Invalid postal code: {postal_code}")
        return None, None

    cp4, cp3 = postal_code[:4], postal_code[4:]
    url = f"https://www.cttcodigopostal.pt/api/v1/d7a547afb5e44e9d93ad7ac31670a32b/{cp4}-{cp3}"
    
    for attempt in range(max_retries):
        time.sleep(2)  # Wait 2 seconds between requests to respect the rate limit
        try:
            response = requests.get(url)
            # Use the handle_response function here
            result = handle_response(response, postal_code)
            if result is not None:  # Successful response
                return result
        except requests.exceptions.RequestException as e:
            logging.error(f"HTTP request failed: {e}")
            if attempt == max_retries - 1:  # Last attempt
                return None, None
    return None, None  # Return None if all attempts failed
    
# Function to enrich data with municipality and district information
def enrich_data(df):
    enriched_data = []
    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = [executor.submit(get_municipality_and_district, postal_code.split(',')[0]) for postal_code in df.iloc[:, 0]]
        for i, future in enumerate(futures):
            try:
                municipality, district = future.result()
            except Exception as e:
                logging.error(f"Error retrieving data for postal code: {df.iloc[i, 0]} - {e}")
                municipality, district = 'Error', 'Error'
            if municipality is not None and district is not None:
                enriched_data.append((df.iloc[i, 0].split(',')[0], municipality, district))
            else:
                enriched_data.append((df.iloc[i, 0].split(',')[0], 'Unknown', 'Unknown'))  # Or log a warning
    logging.info(f"Enriched data: {enriched_data}")
    return enriched_data

# Function to save enriched data to a database
def save_to_database(enriched_data):
    with sqlite3.connect('codigos_postais_database.db') as conn:
        cursor = conn.cursor()
        for row in enriched_data:
            try:
                cursor.execute("INSERT INTO postal_codes VALUES (?, ?, ?)", row)
            except sqlite3.Error as e:
                logging.error(f"Error inserting data: {e}")

# Create a Flask app
def create_app():
    app = Flask(__name__)

    @app.route('/postal_codes', methods=['GET'])
    def get_postal_codes():
        try:
            with sqlite3.connect('codigos_postais_database.db') as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM postal_codes")
                data = cursor.fetchall()
                if not data:
                    return jsonify({"message": "No postal codes found."}), 404
                return jsonify([dict(row) for row in data])
        except Exception as e:
            logging.error(f"Database error: {e}")
            return jsonify({"message": "Error retrieving postal codes."}), 500

    return app

# Function to export data to a new CSV file
def export_to_csv():
    conn = sqlite3.connect('codigos_postais_database.db')
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM postal_codes")
    data = cursor.fetchall()
    conn.close()

    with open('codigos_postais_enriched.csv', 'w', newline='') as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(['Código Postal', 'Município', 'Distrito'])
        writer.writerows(data)

# Function to export the test report to a text file
def export_test_report(test_cases, test_results, defects):
    with open('relatorio_de_testes.txt', 'w') as f:
        f.write("Test Report:\n")
        f.write("------------\n")
        for test_case in test_cases:
            f.write(f"Test Case: {test_case['test_case']}\n")
            f.write(f"Functionality: {test_case['functionality']}\n")
            f.write(f"Actions: {test_case['actions']}\n")
            f.write(f"Expected Result: {test_case['expected_result']}\n\n")

        f.write("Test Results:\n")
        f.write("------------\n")
        for test_result in test_results:
            f.write(f"Test Case: {test_result['test_case']}\n")
            f.write(f"Result: {test_result['result']}\n\n")

        f.write("Defects:\n")
        f.write("--------\n")
        for defect in defects:
            f.write(f"Defect: {defect['defect']}\n")
            f.write(f"Severity: {defect['severity']}\n")
            f.write(f"Description: {defect['description']}\n")
            f.write(f"Resolution Status: {defect['resolution_status']}\n\n")

# Main execution flow
if __name__ == '__main__':
    df = read_csv('codigos_postais.csv')
    enriched_data = enrich_data(df)
    save_to_database(enriched_data)

    app = create_app()
    app.run(debug=True)

    export_to_csv()

    # Define your test cases, results, and defects
    test_cases = [
        {
            'test_case': 'Validate Postal Code Format',
            'functionality': 'Check if the postal code is formatted correctly',
            'actions': 'Input a postal code with invalid characters',
            'expected_result': 'Receive an error message indicating invalid format'
        },
        {
            'test_case': 'Fetch Municipality and District',
            'functionality': 'API call to fetch data based on postal code',
            'actions': 'Input a valid postal code',
            'expected_result': 'Receive correct municipality and district data'
        },
        {
            'test_case': 'Database Insertion',
            'functionality': 'Save enriched data to the database',
            'actions': 'Insert a valid record into the database',
            'expected_result': 'Record should be saved without errors'
        }
    ]

    test_results = [
        {
            'test_case': 'Validate Postal Code Format',
            'result': 'Passed',
            'notes': 'Error message displayed correctly for invalid formats.'
        },
        {
            'test_case': 'Fetch Municipality and District',
            'result': 'Failed',
            'notes': 'API returned a 404 error for an existing postal code.'
        },
        {
            'test_case': 'Database Insertion',
            'result': 'Passed',
            'notes': 'Record saved successfully without errors.'
        }
    ]

    defects = [
        {
            'defect': 'API Failure for Certain Postal Codes',
            'severity': 'High',
            'description': 'The API returns a 404 for certain valid postal codes.',
            'resolution_status': 'Open'
        },
        {
            'defect': 'Database Insertion Error',
            'severity': 'Medium',
            'description': 'Occasional database insertion errors due to constraints.',
            'resolution_status': 'In Progress'
        }
    ]

    export_test_report(test_cases, test_results, defects)