
# Anthoscope
Anthoscope is an interactive web platform designed to help people manage their pollen allergies more effectively. It combines real-time pollen data, user input, and geospatial visualization to deliver clear, map-based insights into allergy risks across regions. Through a color-coded map, users can instantly identify safe or high-risk areas based on pollen concentration. What makes Anthoscope unique is its community-driven component: users can share their personal experiences and rate areas according to their allergy symptoms. This feedback loop creates a continuously improving, human-centered database that complements scientific forecasts with lived experiences. By combining environmental data and citizen input, Anthoscope promotes public awareness and healthier decisions for individuals with allergies, supporting both preventive healthcare and outdoor well-being. The project prototype already visualizes pollen data on an interactive map, marking the first step toward a comprehensive environmental health platform.
## Contributors
The team behind Anthoscope:
- **Alexandros Mylonas,** University of Bonn
- **Evaggelia Patsatzaki,** Aristotle University of Thessaloniki
- **Nikos Chatzis,** Aristotle University of Thessaloniki
- **Georgios Vellios,** International Hellenic University
- **Maria Maragkou,** Technical University of Madrid
- **Grigoris Kaitzis,** Aristotle University of Thessaloniki


## Installation

To install and run the code, you have to clone the repository to your computer usen the following command line:
```bash
  git clone https://github.com/almylonas/anthoscope
```
Install all the required libraries, using the command:
```bash
  cd anthoscope
  pip install -r requirements.txt
```

## Database setup and run locally

To setup the databse, you need to install [PostgreSQL](https://www.postgresql.org/) locally on your system.
Then, open your terminal and connect to PostgreSQL:
```bash
psql -U postgres
```
Then run the SQL setup script:
```bash
\i setup_database.sql
```
You can exit psql with `\q`
Then, test the database connection (optional):
```bash
python -c "import psycopg2; conn = psycopg2.connect(dbname='pollen_db', user='postgres', password='postgres', host='localhost'); print('Connection successful!'); conn.close()"
```
Finally, run the application:
```bash
python app.py
```
The app should start on `http://localhost:5000`
