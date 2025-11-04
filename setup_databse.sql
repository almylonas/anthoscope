-- Create the database (run this as postgres superuser)
CREATE DATABASE pollen_db;

-- Connect to the database
\c pollen_db;

-- Create the allergy_reviews table
CREATE TABLE allergy_reviews (
    id SERIAL PRIMARY KEY,
    center_lat DOUBLE PRECISION NOT NULL,
    center_lng DOUBLE PRECISION NOT NULL,
    radius_km DOUBLE PRECISION NOT NULL,
    pollen_type VARCHAR(50) NOT NULL,
    severity VARCHAR(20) NOT NULL,
    symptoms TEXT[],
    review_text TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create indexes for better query performance
CREATE INDEX idx_pollen_type ON allergy_reviews(pollen_type);
CREATE INDEX idx_created_at ON allergy_reviews(created_at DESC);
CREATE INDEX idx_location ON allergy_reviews(center_lat, center_lng);

-- Optional: Create a view for summary statistics
CREATE VIEW review_summary AS
SELECT 
    pollen_type,
    severity,
    COUNT(*) as review_count,
    AVG(radius_km) as avg_radius_km
FROM allergy_reviews
GROUP BY pollen_type, severity;