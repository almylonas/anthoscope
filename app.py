from flask import Flask, render_template, request, jsonify
import ee
import json
from datetime import datetime, timedelta

app = Flask(__name__)

# Initialize Earth Engine
try:
    ee.Authenticate()
    ee.Initialize(project='nsa-agroai')
except Exception as e:
    print(f"Earth Engine initialization error: {e}")
    print("Please run 'earthengine authenticate' first")

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/calculate-ndvi', methods=['POST'])
def calculate_ndvi():
    try:
        data = request.get_json()
        geometry = data.get('geometry')
        target_date = data.get('target_date')
        
        if not geometry:
            return jsonify({'error': 'No geometry provided'}), 400
        
        if not target_date:
            return jsonify({'error': 'No target date provided'}), 400
        
        # Convert GeoJSON geometry to Earth Engine geometry
        ee_geometry = ee.Geometry.Polygon(geometry['coordinates'])
        
        # Parse target date and create a search window (±30 days)
        target = ee.Date(target_date)
        start = target.advance(-30, 'day')
        end = target.advance(30, 'day')
        
        # Get MODIS NDVI data (MOD13Q1 - 250m 16-day NDVI)
        modis = ee.ImageCollection('MODIS/061/MOD13Q1') \
            .select('NDVI') \
            .filterBounds(ee_geometry) \
            .filterDate(start, end)
        
        # Check if collection is empty
        collection_size = modis.size().getInfo()
        if collection_size == 0:
            return jsonify({'error': 'No MODIS data available within 30 days of the target date'}), 400
        
        # Find the image closest to the target date
        def add_date_diff(image):
            diff = ee.Number(image.get('system:time_start')).subtract(target.millis()).abs()
            return image.set('date_diff', diff)
        
        modis_with_diff = modis.map(add_date_diff)
        closest_image = modis_with_diff.sort('date_diff').first()
        
        # Get the date of the closest image
        date_millis = closest_image.get('system:time_start').getInfo()
        image_date = datetime.fromtimestamp(date_millis / 1000)
        date_str = image_date.strftime('%Y-%m-%d')
        
        # Calculate days difference
        target_datetime = datetime.strptime(target_date, '%Y-%m-%d')
        days_diff = (image_date - target_datetime).days
        
        # Calculate mean NDVI over the polygon
        ndvi_stats = closest_image.reduceRegion(
            reducer=ee.Reducer.mean(),
            geometry=ee_geometry,
            scale=250,
            maxPixels=1e9
        ).getInfo()
        
        ndvi_value = ndvi_stats.get('NDVI')
        
        if ndvi_value is None:
            return jsonify({'error': 'No NDVI data available for this area'}), 400
        
        # Scale NDVI value (MODIS stores values multiplied by 10000)
        ndvi_scaled = ndvi_value / 10000.0
        
        return jsonify({
            'ndvi': ndvi_scaled,
            'date': date_str,
            'days_difference': days_diff,
            'satellite': 'MODIS Terra',
            'product': 'MOD13Q1'
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)