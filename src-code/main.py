import csv
import requests
import logging
import sqlite3
import locale
import time
import sys
import pandas as pd
from concurrent.futures import ThreadPoolExecutor

locale.setlocale(locale.LC_ALL, 'pt_PT.UTF-8')

# Configure logging at the beginning of your script
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s',
                    filename='test_report.log',  # Log to a file named 'app.log'
                    filemode='a')  # Append mode

# File to store invalid postal codes
INVALID_POSTAL_CODES_FILE = 'codigos_postais_invalidos.csv'

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

# Main execution flow
if __name__ == '__main__':
    df = read_csv('codigos_postais.csv')
    enriched_data = enrich_data(df)

    export_to_csv()

    sys.exit()
