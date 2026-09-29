import pandas as pd
from jinja2 import Environment, FileSystemLoader
import os

# 1. Load the data from your CSV file
try:
    data = pd.read_csv('locations_database.csv')
except FileNotFoundError:
    print("Error: 'locations_database.csv' not found. Please ensure it is in the same folder.")
    exit()

# 2. Set up the Jinja2 Template Environment
try:
    env = Environment(loader=FileSystemLoader('.'))
    template = env.get_template('template.html')
except Exception as e:
    print(f"Error loading template: {e}")
    exit()

# 3. Create an output folder for the generated pages
output_dir = 'output'
os.makedirs(output_dir, exist_ok=True)

# 4. Loop through every row in the CSV and generate a page
for index, row in data.iterrows():
    # Replace any empty cells (NaN) with an empty string to avoid errors
    row = row.fillna('')
    
    # Extract the slug to create the folder name
    slug = str(row['slug']).strip()
    
    if not slug:
        continue # Skip empty rows

    # Render the HTML with variables from the current spreadsheet row
    # Uses .get() for keywords as a fallback just in case the column is missing
    html_content = template.render(
        meta_title=row['meta_title'],
        meta_desc=row['meta_desc'],
        keywords=row.get('keywords', 'AC dormitory Kochi, budget stay Aluva, backpackers hostel Kerala'),
        hero_headline=row['hero_headline'],
        distance_km=row['distance_km'],
        travel_time_mins=row['travel_time_mins'],
        location_name=row['location_name'],
        unique_perk=row['unique_perk'],
        map_embed_url=row['map_embed_url']
    )
    
    # Save the generated HTML to a folder matching the slug name
    # We save it as index.html inside the folder to create clean URLs (e.g., cowboydorms.com/slug/)
    page_dir = os.path.join(output_dir, slug)
    os.makedirs(page_dir, exist_ok=True)
    
    file_path = os.path.join(page_dir, 'index.html')
    
    # Write the file using UTF-8 encoding to support all characters/emojis
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(html_content)
        
    print(f"Successfully generated: /{slug}/")

print(f"\nDone! Generated {len(data)} highly-optimized location pages in the '{output_dir}' folder.")
