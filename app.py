from flask import Flask, render_template, request, jsonify, session
import google.generativeai as genai
import threading
from dotenv import load_dotenv
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import os
import socket
import re

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('FLASK_SECRET_KEY', 'default-secret-key')
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('SQLALCHEMY_DATABASE_URI', 'sqlite:///meals.db')
db = SQLAlchemy(app)

def get_local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return '0.0.0.0'

class Meal(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    device_id = db.Column(db.String(50), nullable=False)
    meal_type = db.Column(db.String(50), nullable=False)
    food_description = db.Column(db.Text, nullable=False)
    analysis = db.Column(db.Text, nullable=False)
    date_added = db.Column(db.DateTime, default=datetime.utcnow)

with app.app_context():
    db.create_all()

genai.configure(api_key=os.getenv('GOOGLE_API_KEY'))

MEAL_TYPES = {
    'breakfast': 'فطار',
    'morning_snack': 'وجبة خفيفة صباحية',
    'lunch': 'غداء',
    'afternoon_snack': 'وجبة خفيفة مسائية',
    'dinner': 'عشاء',
    'evening_snack': 'وجبة خفيفة ليلية'
}

def extract_calories(text):
    pattern = r'(\d+)\s*سعرة حرارية'
    match = re.search(pattern, text)
    if match:
        return int(match.group(1))
    return 0

@app.template_filter('regex_search')
def regex_search(text, pattern):
    return re.search(pattern, text)

def get_device_id():
    if 'device_id' not in session:
        session['device_id'] = os.urandom(24).hex()
    return session['device_id']

def calculate_calories(food_description):
    prompt = f"""
    قم بتحليل السعرات الحرارية للطعام التالي:
    {food_description}
    
    اكتب التحليل بالشكل التالي:
    السعرات الحرارية: [الرقم] سعرة حرارية

    البروتين: [الرقم] جرام
    الكربوهيدرات: [الرقم] جرام
    الدهون: [الرقم] جرام

    نصائح صحية:
    - نصيحة 1
    - نصيحة 2
    - نصيحة 3
    """
    
    model = genai.GenerativeModel('gemini-pro')
    response = model.generate_content(prompt)
    return response.text

def calculate_total_calories(meals_data):
    total_calories = 0
    for meal_type, meals_list in meals_data.items():
        for meal in meals_list:
            # Extract numbers followed by "سعرة" from the analysis text
            import re
            matches = re.findall(r'(\d+)\s*سعرة', meal['analysis'])
            if matches:
                # Take the first number found
                calories = int(matches[0])
                total_calories += calories
    return total_calories

def extract_nutritional_values(analysis_text):
    values = {
        'calories': 0,
        'protein': 0,
        'carbs': 0,
        'fats': 0
    }
    
    # Extract calories
    calories_match = re.search(r'(\d+)\s*سعرة', analysis_text)
    if calories_match:
        values['calories'] = int(calories_match.group(1))
    
    # Extract protein
    protein_match = re.search(r'البروتين:.*?(\d+)', analysis_text)
    if protein_match:
        values['protein'] = int(protein_match.group(1))
    
    # Extract carbs
    carbs_match = re.search(r'الكربوهيدرات:.*?(\d+)', analysis_text)
    if carbs_match:
        values['carbs'] = int(carbs_match.group(1))
    
    # Extract fats
    fats_match = re.search(r'الدهون:.*?(\d+)', analysis_text)
    if fats_match:
        values['fats'] = int(fats_match.group(1))
        
    return values

@app.route('/')
def home():
    device_id = get_device_id()
    meals_data = Meal.query.filter_by(device_id=device_id).order_by(Meal.date_added.desc()).all()
    organized_meals = {}
    total_nutrition = {'calories': 0, 'protein': 0, 'carbs': 0, 'fats': 0}
    
    for meal in meals_data:
        if meal.meal_type not in organized_meals:
            organized_meals[meal.meal_type] = []
            
        nutrition = extract_nutritional_values(meal.analysis)
        
        # Add to totals
        for key in total_nutrition:
            total_nutrition[key] += nutrition[key]
            
        organized_meals[meal.meal_type].append({
            'food': meal.food_description,
            'analysis': meal.analysis,
            'date': meal.date_added.strftime('%Y-%m-%d %H:%M'),
            'nutrition': nutrition
        })
    
    total_calories = calculate_total_calories(organized_meals)
    
    return render_template('index.html', 
                         meal_types=MEAL_TYPES, 
                         meals=organized_meals,
                         total_calories=total_calories,
                         total_nutrition=total_nutrition)

@app.route('/add_meal', methods=['POST'])
def add_meal():
    meal_type = request.form.get('meal_type')
    food = request.form.get('food')
    device_id = get_device_id()
    
    result = calculate_calories(food)
    
    new_meal = Meal(
        device_id=device_id,
        meal_type=meal_type,
        food_description=food,
        analysis=result
    )
    
    db.session.add(new_meal)
    db.session.commit()
    
    return jsonify({
        'result': result,
        'meal_type': meal_type,
        'date': new_meal.date_added.strftime('%Y-%m-%d %H:%M')
    })

@app.route('/clear_meals', methods=['POST'])
def clear_meals():
    device_id = get_device_id()
    Meal.query.filter_by(device_id=device_id).delete()
    db.session.commit()
    return jsonify({'status': 'success'})
@app.template_filter('regex_findall')
def regex_findall(text, pattern):
    import re
    matches = re.findall(pattern, text)
    return matches if matches else ['0']




if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)
    



