import csv
import requests
import logging
import sqlite3
import locale
import time
import sys
import os
import pandas as pd
from flask import Flask, request, render_template, jsonify
from concurrent.futures import ThreadPoolExecutor

locale.setlocale(locale.LC_ALL, 'pt_PT.UTF-8')

# Configure logging at the beginning of your script
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s',
                    filename='test_report.log',  # Log to a file named 'app.log'
                    filemode='a')  # Append mode

# File to store invalid postal codes
INVALID_POSTAL_CODES_FILE = 'codigos_postais_invalidos.csv'

app = Flask(__name__, static_url_path='', static_folder='src-code')

# Function to read the CSV file
def read_csv(file_path):
    return pd.read_csv(file_path)

# Function to check if the file exists and has data
def check_file(file_path):
    if os.path.exists(file_path) and os.path.getsize(file_path) > 0:
        logging.info(f"The file '{file_path}' exists and contains data.")
        return True
    else:
        logging.warning(f"The file '{file_path}' does not exist or is empty.")
        return False
    
# Function to read invalid postal codes from the CSV file
def read_invalid_postal_codes():
    try:
        invalid_postal_codes = pd.read_csv(INVALID_POSTAL_CODES_FILE, header=None)
        return set(invalid_postal_codes[0].str.strip())
    except FileNotFoundError:
        logging.error(f"The file '{INVALID_POSTAL_CODES_FILE}' was not found.")
        return set()

# Function to check if the postal code is in the enriched CSV file
def check_enriched_postal_code(postal_code):
    try:
        enriched_data = pd.read_csv('codigos_postais_enriched.csv')
        if postal_code in enriched_data['Código Postal'].values:
            logging.info(f"Postal code {postal_code} found in enriched data.")
            return True
        else:
            logging.info(f"Postal code {postal_code} not found in enriched data.")
            return False
    except FileNotFoundError:
        logging.error("The file 'codigos_postais_enriched.csv' was not found.")
        return False
    
    # Function to check if the postal code is in the SQLite database
def check_database_postal_code(postal_code):
    try:
        with sqlite3.connect('codigos_postais_database.db') as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM postal_codes WHERE codigo_postal=?", (postal_code,))
            result = cursor.fetchone()
            if result:
                logging.info(f"Postal code {postal_code} found in the database.")
                return True
            else:
                logging.info(f"Postal code {postal_code} not found in the database.")
                return False
    except sqlite3.Error as e:
        logging.error(f"Database error: {e}")
        return False
    
# Function to enrich postal codes and export them to CSV
def enrich_and_export_data():
    # Enrichment process will only run if files do not exist or are empty
    if not (check_file('codigos_postais_invalidos.csv') and 
            check_file('codigos_postais_enriched.csv') and 
            check_file('codigos_postais_database.db')):
        
        logging.info("Files are missing or empty. Enriching and exporting data.")

        # Assume these functions are defined elsewhere
        df = pd.read_csv('codigos_postais.csv')  # Read main postal code CSV
        enriched_data = enrich_data(df)  # Enrich the data
        export_to_csv(enriched_data)  # Export enriched data to CSV
        logging.info("Data enrichment and export completed.")
        
    else:
        logging.info("Files exist and contain data. Skipping enrichment and export process.")
    
# Function to check the validity of a postal code
def check_postal_code_validity(postal_code):
    # Check if the files exist and contain data
    files_exist = check_file('codigos_postais_invalidos.csv') and \
                  check_file('codigos_postais_enriched.csv') and \
                  check_file('codigos_postais_database.db')

    if not files_exist:
        logging.error("One or more required files do not exist or are empty.")
        return False

    # Load invalid postal codes
    invalid_postal_codes = read_invalid_postal_codes()

    # Check if the postal code is invalid
    if postal_code in invalid_postal_codes:
        logging.info(f"Postal code {postal_code} is invalid (found in 'codigos_postais_invalidos.csv').")
        return False

    # Check if the postal code exists in enriched CSV or database
    if check_enriched_postal_code(postal_code) or check_database_postal_code(postal_code):
        logging.info(f"Postal code {postal_code} is valid.")
        return True
    else:
        logging.info(f"Postal code {postal_code} is invalid (not found in enriched data or database).")
        return False

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

# Function to save enriched data to a database
def save_to_database(postal_code, municipality, district):
    if municipality is None or district is None:
        logging.warning(f"Skipping insertion for postal code {postal_code} due to NULL values.")
        # Register invalid postal codes
        # Format
        formatted_postal_code = f"{postal_code[:4]}-{postal_code[4:]}"
        log_invalid_postal_code(formatted_postal_code)
        return

    try:
        # Format
        formatted_postal_code = f"{postal_code[:4]}-{postal_code[4:]}"

        with sqlite3.connect('codigos_postais_database.db') as conn:
            cursor = conn.cursor()
            cursor.execute("""CREATE TABLE IF NOT EXISTS postal_codes (
                codigo_postal VARCHAR(8) PRIMARY KEY,
                concelho VARCHAR(255),
                distrito VARCHAR(255)
            )""")
            try:
                cursor.execute("INSERT INTO postal_codes (codigo_postal, concelho, distrito) VALUES (?, ?, ?)",
                               (formatted_postal_code, municipality, district))
            except sqlite3.IntegrityError:
                logging.warning(f"Postal code {formatted_postal_code} already exists in the database.")
    except sqlite3.Error as e:
        logging.error(f"Database connection error: {e}")

# Function to log invalid postal codes
def log_invalid_postal_code(formatted_postal_code):
    with open(INVALID_POSTAL_CODES_FILE, 'a', newline='') as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow([formatted_postal_code])  # Write the invalid postal code

# Function to get municipality and district information
def get_municipality_and_district(postal_code, max_retries=3):
    logging.info(f"Fetching data for postal code: {postal_code}")
    postal_code = postal_code.strip().replace(",", "").replace(" ", "").replace("-", "").zfill(7)

    if len(postal_code) < 7 or len(postal_code) > 8 or not postal_code.isdigit():
        logging.warning(f"Invalid postal code: {postal_code}")
        return None, None

    cp4, cp3 = postal_code[:4], postal_code[4:]
    url = f"https://www.cttcodigopostal.pt/api/v1/d7a547afb5e44e9d93ad7ac31670a32b/{cp4}-{cp3}"

    # Define a variable to keep track of request count and time
    if not hasattr(get_municipality_and_district, "request_count"):
        get_municipality_and_district.request_count = 0
        get_municipality_and_district.start_time = time.time()

    # Check if the maximum request limit has been reached
    if get_municipality_and_district.request_count >= 30:
        elapsed_time = time.time() - get_municipality_and_district.start_time
        if elapsed_time < 60:  # If less than a minute has passed
            wait_time = 60 - elapsed_time
            logging.info(f"Rate limit reached. Waiting for {wait_time:.2f} seconds.")
            time.sleep(wait_time)  # Wait until a minute has passed
        # Reset the counter and start time
        get_municipality_and_district.request_count = 0
        get_municipality_and_district.start_time = time.time()
    
    for attempt in range(max_retries):
        time.sleep(2)  # Wait 2 seconds between requests to respect the rate limit
        try:
            response = requests.get(url)
            # Increment the request count
            get_municipality_and_district.request_count += 1
            # Use the handle_response function here
            result = handle_response(response, postal_code)
            if result is not None:  # Successful response
                municipality, district = result
                save_to_database(postal_code, municipality, district)  # Save to database
                return municipality, district
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
                enriched_data.append((df.iloc[i, 0].split(',')[0], 'Unknown', 'Unknown'))
    logging.info(f"Enriched data to save: {enriched_data}")
    return enriched_data

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

# Function to get data from the SQLite database
def get_postal_codes():
    conn = sqlite3.connect('codigos_postais_database.db')
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM postal_codes")
    rows = cursor.fetchall()
    conn.close()
    return rows

invalid_postal_codes = set()  

def load_invalid_postal_codes(filename):
    invalid_postal_codes = set()
    with open(filename, mode='r', encoding='utf-8') as file:
        reader = csv.reader(file)
        for row in reader:
            invalid_postal_codes.add(row[0].strip())
    return invalid_postal_codes

@app.route('/')
def template():
    return render_template('index.html')

# API endpoint to get all postal codes
@app.route('/postal_codes', methods=['GET'])
def get_all_postal_codes():
    try:
        postal_codes = get_postal_codes()
        if postal_codes:
            return jsonify(postal_codes), 200  # Return the data as JSON with status code 200 (OK)
        else:
            return jsonify({"message": "No postal codes found"}), 404  # No data found
    except sqlite3.Error as e:
        logging.error(f"Database error: {e}")
        return jsonify({"error": "Internal Server Error"}), 500  # Return status code 500 (Internal Server Error)

# API endpoint to get postal code by code
@app.route('/postal_codes/<codigo_postal>', methods=['GET'])
def get_postal_code(codigo_postal):
    try:
        conn = sqlite3.connect('codigos_postais_database.db')
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM postal_codes WHERE codigo_postal=?", (codigo_postal,))
        postal_code = cursor.fetchone()
        conn.close()
        if postal_code:
            return jsonify(postal_code), 200  # Return the postal code data with status code 200 (OK)
        else:
            return jsonify({"message": "Postal code not found"}), 404  # Postal code not found
    except sqlite3.Error as e:
        logging.error(f"Database error: {e}")
        return jsonify({"error": "Internal Server Error"}), 500  # Return status code 500 (Internal Server Error)

@app.route('/verify_postal_code', methods=['POST'])
def verify_postal_code():
    data = request.get_json()
    postal_code = data.get('postal_code', '').strip()

    invalid_postal_codes = load_invalid_postal_codes(INVALID_POSTAL_CODES_FILE)

    if len(postal_code) != 8 or postal_code[4] != '-' or not postal_code.replace("-", "").isdigit():
        logging.warning("Invalid postal code format. Expected format is 'XXXX-XXX'.")
        return jsonify({'message': 'Formato de código postal inválido.'}), 400

    if postal_code in invalid_postal_codes:
        return jsonify({'message': 'Código postal inválido.'}), 400

    try:
        conn = sqlite3.connect('codigos_postais_database.db')
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM postal_codes WHERE codigo_postal=?", (postal_code,))
        postal_code_data = cursor.fetchone()
        if postal_code_data:
            logging.info(f"Código postal encontrado: {postal_code_data}")
            return jsonify({'message': 'Código postal válido.'}), 200
        
        logging.warning("Código postal não encontrado no banco de dados.")
        return jsonify({'message': 'Código postal não encontrado.'}), 404 
    except sqlite3.Error as e:
        logging.error(f"Database error: {e}")
        return jsonify({"error": "Internal Server Error"}), 500
    finally:
        conn.close()


# Main execution flow
if __name__ == '__main__':

    enrich_and_export_data()
    app.run(debug=True)
    sys.exit()