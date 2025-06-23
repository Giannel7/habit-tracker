from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3
import psycopg
from datetime import datetime, timedelta
import os
from collections import defaultdict, Counter

app = Flask(__name__)
# Use environment variable for secret key in production, fallback for development
app.secret_key = os.environ.get('SECRET_KEY', 'your-secret-key-change-this-in-production')

# Database setup - PostgreSQL for production, SQLite for local development
DATABASE_URL = os.environ.get('DATABASE_URL')
IS_PRODUCTION = DATABASE_URL is not None

if IS_PRODUCTION:
    # Production: Use PostgreSQL
    DATABASE = DATABASE_URL
else:
    # Local development: Use SQLite
    DATABASE = 'habits.db'

def get_db_connection():
    """Create database connection with proper error handling for both PostgreSQL and SQLite"""
    try:
        if IS_PRODUCTION:
            # PostgreSQL connection with psycopg
            conn = psycopg.connect(DATABASE_URL)
            conn.autocommit = True
            return conn
        else:
            # SQLite connection
            conn = sqlite3.connect(DATABASE)
            conn.row_factory = sqlite3.Row
            return conn
    except Exception as e:
        print(f"Database connection error: {e}")
        return None

def init_db():
    """Initialize database with tables and sample data"""
    conn = get_db_connection()
    if not conn:
        return False
    
    try:
        if IS_PRODUCTION:
            # PostgreSQL table creation
            cursor = conn.cursor()
            
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    id SERIAL PRIMARY KEY,
                    username VARCHAR(255) UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS habits (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES users(id),
                    name TEXT NOT NULL,
                    description TEXT,
                    category TEXT NOT NULL,
                    active BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS habit_entries (
                    id SERIAL PRIMARY KEY,
                    habit_id INTEGER NOT NULL REFERENCES habits(id),
                    date DATE NOT NULL,
                    completed BOOLEAN NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(habit_id, date)
                )
            ''')
            
        else:
            # SQLite table creation (existing code)
            conn.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            conn.execute('''
                CREATE TABLE IF NOT EXISTS habits (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    name TEXT NOT NULL,
                    description TEXT,
                    category TEXT NOT NULL,
                    active BOOLEAN DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users (id)
                )
            ''')
            
            conn.execute('''
                CREATE TABLE IF NOT EXISTS habit_entries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    habit_id INTEGER NOT NULL,
                    date DATE NOT NULL,
                    completed BOOLEAN NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (habit_id) REFERENCES habits (id),
                    UNIQUE(habit_id, date)
                )
            ''')
            
            conn.commit()
        
        print("Database initialized successfully!")
        return True
        
    except Exception as e:
        print(f"Database initialization error: {e}")
        return False
    finally:
        conn.close()

def execute_query(query, params=None, fetch=False, fetchone=False):
    """Universal database query executor for both PostgreSQL and SQLite"""
    conn = get_db_connection()
    if not conn:
        return None
    
    try:
        if IS_PRODUCTION:
            cursor = conn.cursor()
            cursor.execute(query, params or ())
            
            if fetchone:
                result = cursor.fetchone()
                if result:
                    # Convert tuple to dict for PostgreSQL
                    columns = [desc[0] for desc in cursor.description]
                    return dict(zip(columns, result))
                return None
            elif fetch:
                results = cursor.fetchall()
                columns = [desc[0] for desc in cursor.description]
                return [dict(zip(columns, row)) for row in results]
            else:
                return cursor.rowcount
        else:
            if fetchone:
                result = conn.execute(query, params or ()).fetchone()
                return dict(result) if result else None
            elif fetch:
                results = conn.execute(query, params or ()).fetchall()
                return [dict(row) for row in results]
            else:
                cursor = conn.execute(query, params or ())
                conn.commit()
                return cursor.lastrowid
                
    except Exception as e:
        print(f"Database query error: {e}")
        return None
    finally:
        conn.close()

def create_sample_habits(user_id):
    """Create sample habits for new users"""
    sample_habits = [
        ("Drink 8 glasses of water", "Stay hydrated throughout the day", "Health"),
        ("Exercise for 30 minutes", "Daily physical activity", "Fitness"),
        ("Read for 20 minutes", "Daily reading habit", "Learning"),
        ("Meditate for 10 minutes", "Mindfulness and relaxation", "Wellness"),
        ("Write in journal", "Daily reflection and thoughts", "Personal")
    ]
    
    conn = get_db_connection()
    if not conn:
        return
    
    try:
        for name, description, category in sample_habits:
            conn.execute(
                'INSERT INTO habits (user_id, name, description, category) VALUES (?, ?, ?, ?)',
                (user_id, name, description, category)
            )
        conn.commit()
    except sqlite3.Error as e:
        print(f"Error creating sample habits: {e}")
    finally:
        conn.close()

# Initialize database on startup
if not os.path.exists(DATABASE):
    init_db()

@app.route('/')
def index():
    """Home page - redirect to dashboard if logged in"""
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    return render_template('index.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    """User registration"""
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        
        # Validation
        if not username or not password:
            flash('Username and password are required!', 'error')
            return render_template('register.html')
        
        if len(username) < 3:
            flash('Username must be at least 3 characters long!', 'error')
            return render_template('register.html')
        
        if len(password) < 6:
            flash('Password must be at least 6 characters long!', 'error')
            return render_template('register.html')
        
        conn = get_db_connection()
        if not conn:
            flash('Database error. Please try again.', 'error')
            return render_template('register.html')
        
        try:
            # Check if username exists
            user = conn.execute('SELECT id FROM users WHERE username = ?', (username,)).fetchone()
            if user:
                flash('Username already exists!', 'error')
                return render_template('register.html')
            
            # Create new user
            password_hash = generate_password_hash(password)
            cursor = conn.execute(
                'INSERT INTO users (username, password_hash) VALUES (?, ?)',
                (username, password_hash)
            )
            user_id = cursor.lastrowid
            conn.commit()
            
            # Create sample habits for new user
            create_sample_habits(user_id)
            
            flash('Registration successful! Please log in.', 'success')
            return redirect(url_for('login'))
            
        except sqlite3.Error as e:
            flash('Registration failed. Please try again.', 'error')
            print(f"Registration error: {e}")
        finally:
            conn.close()
    
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    """User login"""
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        
        if not username or not password:
            flash('Username and password are required!', 'error')
            return render_template('login.html')
        
        conn = get_db_connection()
        if not conn:
            flash('Database error. Please try again.', 'error')
            return render_template('login.html')
        
        try:
            user = conn.execute(
                'SELECT id, username, password_hash FROM users WHERE username = ?',
                (username,)
            ).fetchone()
            
            if user and check_password_hash(user['password_hash'], password):
                session['user_id'] = user['id']
                session['username'] = user['username']
                flash('Login successful!', 'success')
                return redirect(url_for('dashboard'))
            else:
                flash('Invalid username or password!', 'error')
                
        except sqlite3.Error as e:
            flash('Login failed. Please try again.', 'error')
            print(f"Login error: {e}")
        finally:
            conn.close()
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    """User logout"""
    session.clear()
    flash('You have been logged out.', 'info')
    return redirect(url_for('index'))

@app.route('/dashboard')
def dashboard():
    """Main dashboard with summary statistics"""
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    conn = get_db_connection()
    if not conn:
        flash('Database error.', 'error')
        return redirect(url_for('index'))
    
    try:
        user_id = session['user_id']
        today = datetime.now().date()
        
        # Get total active habits
        total_habits = conn.execute(
            'SELECT COUNT(*) as count FROM habits WHERE user_id = ? AND active = 1',
            (user_id,)
        ).fetchone()['count']
        
        # Get today's completed habits
        completed_today = conn.execute('''
            SELECT COUNT(*) as count FROM habit_entries he
            JOIN habits h ON he.habit_id = h.id
            WHERE h.user_id = ? AND he.date = ? AND he.completed = 1 AND h.active = 1
        ''', (user_id, today)).fetchone()['count']
        
        # Calculate overall completion rate (last 30 days)
        thirty_days_ago = today - timedelta(days=30)
        completion_stats = conn.execute('''
            SELECT 
                COUNT(*) as total_entries,
                SUM(CASE WHEN completed = 1 THEN 1 ELSE 0 END) as completed_entries
            FROM habit_entries he
            JOIN habits h ON he.habit_id = h.id
            WHERE h.user_id = ? AND he.date >= ? AND h.active = 1
        ''', (user_id, thirty_days_ago)).fetchone()
        
        completion_rate = 0
        if completion_stats['total_entries'] > 0:
            completion_rate = round((completion_stats['completed_entries'] / completion_stats['total_entries']) * 100)
        
        # Count habits with active streaks (current streaks > 0)
        habits = conn.execute('''
            SELECT id, name FROM habits 
            WHERE user_id = ? AND active = 1
        ''', (user_id,)).fetchall()
        
        active_streaks = 0
        for habit in habits:
            streak = calculate_current_streak(habit['id'], conn)
            if streak > 0:
                active_streaks += 1
        
        # Get recent activity (last 7 days)
        week_ago = today - timedelta(days=7)
        recent_entries = conn.execute('''
            SELECT he.date, he.completed, h.name as habit_name
            FROM habit_entries he
            JOIN habits h ON he.habit_id = h.id
            WHERE h.user_id = ? AND he.date >= ? AND h.active = 1
            ORDER BY he.date DESC, h.name
        ''', (user_id, week_ago)).fetchall()
        
        return render_template('dashboard.html',
                             total_habits=total_habits,
                             completed_today=completed_today,
                             completion_rate=completion_rate,
                             active_streaks=active_streaks,
                             recent_entries=recent_entries,
                             today_str=today.strftime('%Y-%m-%d'))
        
    except sqlite3.Error as e:
        flash('Error loading dashboard.', 'error')
        print(f"Dashboard error: {e}")
        return redirect(url_for('index'))
    finally:
        conn.close()

@app.route('/habits')
def habits():
    """Manage habits page"""
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    conn = get_db_connection()
    if not conn:
        flash('Database error.', 'error')
        return redirect(url_for('index'))
    
    try:
        user_id = session['user_id']
        habits = conn.execute('''
            SELECT id, name, description, category, active, created_at
            FROM habits 
            WHERE user_id = ? 
            ORDER BY 
                CASE category 
                    WHEN 'Health' THEN 1
                    WHEN 'Fitness' THEN 2
                    WHEN 'Learning' THEN 3
                    WHEN 'Wellness' THEN 4
                    WHEN 'Personal' THEN 5
                    ELSE 6
                END, name
        ''', (user_id,)).fetchall()
        
        return render_template('habits.html', habits=habits)
        
    except sqlite3.Error as e:
        flash('Error loading habits.', 'error')
        print(f"Habits error: {e}")
        return redirect(url_for('dashboard'))
    finally:
        conn.close()

@app.route('/add_habit', methods=['GET', 'POST'])
def add_habit():
    """Add new habit"""
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        description = request.form.get('description', '').strip()
        category = request.form.get('category', '').strip()
        
        if not name or not category:
            flash('Habit name and category are required!', 'error')
            return render_template('add_habit.html')
        
        conn = get_db_connection()
        if not conn:
            flash('Database error.', 'error')
            return render_template('add_habit.html')
        
        try:
            conn.execute(
                'INSERT INTO habits (user_id, name, description, category) VALUES (?, ?, ?, ?)',
                (session['user_id'], name, description, category)
            )
            conn.commit()
            flash('Habit added successfully!', 'success')
            return redirect(url_for('habits'))
            
        except sqlite3.Error as e:
            flash('Error adding habit.', 'error')
            print(f"Add habit error: {e}")
        finally:
            conn.close()
    
    return render_template('add_habit.html')

@app.route('/edit_habit/<int:habit_id>', methods=['GET', 'POST'])
def edit_habit(habit_id):
    """Edit existing habit"""
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    conn = get_db_connection()
    if not conn:
        flash('Database error.', 'error')
        return redirect(url_for('habits'))
    
    try:
        # Get habit details
        habit = conn.execute(
            'SELECT * FROM habits WHERE id = ? AND user_id = ?',
            (habit_id, session['user_id'])
        ).fetchone()
        
        if not habit:
            flash('Habit not found!', 'error')
            return redirect(url_for('habits'))
        
        if request.method == 'POST':
            name = request.form.get('name', '').strip()
            description = request.form.get('description', '').strip()
            category = request.form.get('category', '').strip()
            active = request.form.get('active') == 'on'
            
            if not name or not category:
                flash('Habit name and category are required!', 'error')
                return render_template('edit_habit.html', habit=habit)
            
            conn.execute('''
                UPDATE habits 
                SET name = ?, description = ?, category = ?, active = ?
                WHERE id = ? AND user_id = ?
            ''', (name, description, category, active, habit_id, session['user_id']))
            conn.commit()
            
            flash('Habit updated successfully!', 'success')
            return redirect(url_for('habits'))
        
        return render_template('edit_habit.html', habit=habit)
        
    except sqlite3.Error as e:
        flash('Error editing habit.', 'error')
        print(f"Edit habit error: {e}")
        return redirect(url_for('habits'))
    finally:
        conn.close()

@app.route('/weekly_view')
def weekly_view():
    """Weekly grid view of habits"""
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    # Get week offset from query parameter
    week_offset = int(request.args.get('week', 0))
    
    # Calculate the start of the week (Monday)
    today = datetime.now().date()
    days_since_monday = today.weekday()
    week_start = today - timedelta(days=days_since_monday) + timedelta(weeks=week_offset)
    
    # Generate week dates
    week_dates = [week_start + timedelta(days=i) for i in range(7)]
    
    conn = get_db_connection()
    if not conn:
        flash('Database error.', 'error')
        return redirect(url_for('dashboard'))
    
    try:
        user_id = session['user_id']
        
        # Get active habits in the same order as habits page
        habits = conn.execute('''
            SELECT id, name, category
            FROM habits 
            WHERE user_id = ? AND active = 1
            ORDER BY 
                CASE category 
                    WHEN 'Health' THEN 1
                    WHEN 'Fitness' THEN 2
                    WHEN 'Learning' THEN 3
                    WHEN 'Wellness' THEN 4
                    WHEN 'Personal' THEN 5
                    ELSE 6
                END, name
        ''', (user_id,)).fetchall()
        
        # Get habit entries for the week
        entries = conn.execute('''
            SELECT habit_id, date, completed
            FROM habit_entries
            WHERE habit_id IN (SELECT id FROM habits WHERE user_id = ? AND active = 1)
            AND date BETWEEN ? AND ?
        ''', (user_id, week_dates[0], week_dates[6])).fetchall()
        
        # Organize entries by habit_id and date
        entries_dict = {}
        for entry in entries:
            if entry['habit_id'] not in entries_dict:
                entries_dict[entry['habit_id']] = {}
            entries_dict[entry['habit_id']][entry['date']] = entry['completed']
        
        # Calculate daily success rates
        daily_stats = []
        for date in week_dates:
            completed = 0
            total = len(habits)
            date_str = date.strftime('%Y-%m-%d')
            
            for habit in habits:
                if habit['id'] in entries_dict and date_str in entries_dict[habit['id']]:
                    if entries_dict[habit['id']][date_str]:
                        completed += 1
                else:
                    total -= 1  # Don't count if no entry exists
            
            success_rate = round((completed / total * 100) if total > 0 else 0)
            daily_stats.append({
                'date': date,
                'success_rate': success_rate,
                'completed': completed,
                'total': total
            })
        
        # Calculate habit success rates for the week
        habit_stats = []
        for habit in habits:
            completed = 0
            total = 0
            
            for date in week_dates:
                date_str = date.strftime('%Y-%m-%d')
                if habit['id'] in entries_dict and date_str in entries_dict[habit['id']]:
                    total += 1
                    if entries_dict[habit['id']][date_str]:
                        completed += 1
            
            success_rate = round((completed / total * 100) if total > 0 else 0)
            habit_stats.append({
                'habit': habit,
                'success_rate': success_rate,
                'completed': completed,
                'total': total
            })
        
        return render_template('weekly_view.html',
                             habits=habits,
                             week_dates=week_dates,
                             entries_dict=entries_dict,
                             week_offset=week_offset,
                             daily_stats=daily_stats,
                             habit_stats=habit_stats)
        
    except sqlite3.Error as e:
        flash('Error loading weekly view.', 'error')
        print(f"Weekly view error: {e}")
        return redirect(url_for('dashboard'))
    finally:
        conn.close()

@app.route('/toggle_habit', methods=['POST'])
def toggle_habit():
    """Toggle habit completion for a specific date via AJAX"""
    if 'user_id' not in session:
        return jsonify({'success': False, 'error': 'Not logged in'})
    
    try:
        data = request.get_json()
        habit_id = int(data['habit_id'])
        date_str = data['date']
        
        # Validate date format
        try:
            date_obj = datetime.strptime(date_str, '%Y-%m-%d').date()
        except ValueError:
            return jsonify({'success': False, 'error': 'Invalid date format'})
        
        conn = get_db_connection()
        if not conn:
            return jsonify({'success': False, 'error': 'Database error'})
        
        # Verify habit belongs to user
        habit = conn.execute(
            'SELECT id FROM habits WHERE id = ? AND user_id = ? AND active = 1',
            (habit_id, session['user_id'])
        ).fetchone()
        
        if not habit:
            conn.close()
            return jsonify({'success': False, 'error': 'Habit not found'})
        
        # Check current entry
        current_entry = conn.execute(
            'SELECT completed FROM habit_entries WHERE habit_id = ? AND date = ?',
            (habit_id, date_str)
        ).fetchone()
        
        if current_entry is None:
            # No entry exists, create as completed
            conn.execute(
                'INSERT INTO habit_entries (habit_id, date, completed) VALUES (?, ?, ?)',
                (habit_id, date_str, True)
            )
            new_status = 'completed'
        elif current_entry['completed']:
            # Currently completed, mark as not completed
            conn.execute(
                'UPDATE habit_entries SET completed = ? WHERE habit_id = ? AND date = ?',
                (False, habit_id, date_str)
            )
            new_status = 'missed'
        else:
            # Currently not completed, delete entry (make it empty)
            conn.execute(
                'DELETE FROM habit_entries WHERE habit_id = ? AND date = ?',
                (habit_id, date_str)
            )
            new_status = 'empty'
        
        conn.commit()
        conn.close()
        return jsonify({'success': True, 'status': new_status})
        
    except (ValueError, KeyError, sqlite3.Error) as e:
        print(f"Toggle habit error: {e}")
        return jsonify({'success': False, 'error': 'Server error'})

def calculate_current_streak(habit_id, conn):
    """Calculate current streak for a habit"""
    today = datetime.now().date()
    
    # Get all entries for this habit, ordered by date descending
    entries = conn.execute('''
        SELECT date, completed FROM habit_entries 
        WHERE habit_id = ? AND date <= ?
        ORDER BY date DESC
    ''', (habit_id, today)).fetchall()
    
    if not entries:
        return 0
    
    # Check if there's a gap from today
    streak = 0
    current_date = today
    
    for entry in entries:
        entry_date = datetime.strptime(entry['date'], '%Y-%m-%d').date()
        
        # If there's a gap, break
        if entry_date < current_date - timedelta(days=1):
            break
        
        # If this date is completed, increment streak
        if entry_date == current_date and entry['completed']:
            streak += 1
            current_date -= timedelta(days=1)
        elif entry_date == current_date and not entry['completed']:
            # If today/yesterday was missed, streak is broken
            break
        elif entry_date < current_date:
            # We've moved past the current date we're checking
            current_date = entry_date
            if entry['completed']:
                streak += 1
            else:
                break
    
    return streak

def calculate_longest_streak(habit_id, conn):
    """Calculate longest streak for a habit"""
    entries = conn.execute('''
        SELECT date, completed FROM habit_entries 
        WHERE habit_id = ? 
        ORDER BY date
    ''', (habit_id,)).fetchall()
    
    if not entries:
        return 0
    
    max_streak = 0
    current_streak = 0
    
    for entry in entries:
        if entry['completed']:
            current_streak += 1
            max_streak = max(max_streak, current_streak)
        else:
            current_streak = 0
    
    return max_streak

@app.route('/analytics')
def analytics():
    """Analytics and insights page"""
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    conn = get_db_connection()
    if not conn:
        flash('Database error.', 'error')
        return redirect(url_for('dashboard'))
    
    try:
        user_id = session['user_id']
        today = datetime.now().date()
        thirty_days_ago = today - timedelta(days=30)
        seven_days_ago = today - timedelta(days=7)
        fourteen_days_ago = today - timedelta(days=14)
        
        # Overall completion rate (last 30 days)
        completion_stats = conn.execute('''
            SELECT 
                COUNT(*) as total_entries,
                SUM(CASE WHEN completed = 1 THEN 1 ELSE 0 END) as completed_entries
            FROM habit_entries he
            JOIN habits h ON he.habit_id = h.id
            WHERE h.user_id = ? AND he.date >= ? AND h.active = 1
        ''', (user_id, thirty_days_ago)).fetchone()
        
        overall_completion_rate = 0
        if completion_stats['total_entries'] > 0:
            overall_completion_rate = round((completion_stats['completed_entries'] / completion_stats['total_entries']) * 100)
        
        # Best day of week analysis
        day_stats = conn.execute('''
            SELECT 
                CASE CAST(strftime('%w', he.date) AS INTEGER)
                    WHEN 0 THEN 'Sunday'
                    WHEN 1 THEN 'Monday'
                    WHEN 2 THEN 'Tuesday'
                    WHEN 3 THEN 'Wednesday'
                    WHEN 4 THEN 'Thursday'
                    WHEN 5 THEN 'Friday'
                    WHEN 6 THEN 'Saturday'
                END as day_name,
                COUNT(*) as total_entries,
                SUM(CASE WHEN completed = 1 THEN 1 ELSE 0 END) as completed_entries
            FROM habit_entries he
            JOIN habits h ON he.habit_id = h.id
            WHERE h.user_id = ? AND he.date >= ? AND h.active = 1
            GROUP BY strftime('%w', he.date)
            HAVING total_entries > 0
            ORDER BY (CAST(completed_entries AS FLOAT) / total_entries) DESC
        ''', (user_id, thirty_days_ago)).fetchall()
        
        best_day = None
        if day_stats:
            best_day = {
                'day': day_stats[0]['day_name'],
                'rate': round((day_stats[0]['completed_entries'] / day_stats[0]['total_entries']) * 100)
            }
        
        # Week comparison (this week vs last week)
        this_week_stats = conn.execute('''
            SELECT 
                COUNT(*) as total_entries,
                SUM(CASE WHEN completed = 1 THEN 1 ELSE 0 END) as completed_entries
            FROM habit_entries he
            JOIN habits h ON he.habit_id = h.id
            WHERE h.user_id = ? AND he.date >= ? AND h.active = 1
        ''', (user_id, seven_days_ago)).fetchone()
        
        last_week_stats = conn.execute('''
            SELECT 
                COUNT(*) as total_entries,
                SUM(CASE WHEN completed = 1 THEN 1 ELSE 0 END) as completed_entries
            FROM habit_entries he
            JOIN habits h ON he.habit_id = h.id
            WHERE h.user_id = ? AND he.date >= ? AND he.date < ? AND h.active = 1
        ''', (user_id, fourteen_days_ago, seven_days_ago)).fetchone()
        
        # Calculate week comparison
        this_week_rate = 0
        last_week_rate = 0
        week_trend = "No data"
        
        if this_week_stats['total_entries'] > 0:
            this_week_rate = round((this_week_stats['completed_entries'] / this_week_stats['total_entries']) * 100)
        
        if last_week_stats['total_entries'] > 0:
            last_week_rate = round((last_week_stats['completed_entries'] / last_week_stats['total_entries']) * 100)
        
        if this_week_rate > 0 and last_week_rate > 0:
            difference = this_week_rate - last_week_rate
            if difference > 0:
                week_trend = f"↑ {difference}% improvement"
            elif difference < 0:
                week_trend = f"↓ {abs(difference)}% decline"
            else:
                week_trend = "→ Same as last week"
        elif this_week_rate > 0:
            week_trend = f"{this_week_rate}% (new data)"
        
        # Individual habit statistics (in same order as weekly view)
        habits = conn.execute('''
            SELECT id, name, category
            FROM habits 
            WHERE user_id = ? AND active = 1
            ORDER BY 
                CASE category 
                    WHEN 'Health' THEN 1
                    WHEN 'Fitness' THEN 2
                    WHEN 'Learning' THEN 3
                    WHEN 'Wellness' THEN 4
                    WHEN 'Personal' THEN 5
                    ELSE 6
                END, name
        ''', (user_id,)).fetchall()
        
        habit_stats = []
        for habit in habits:
            # Current streak
            current_streak = calculate_current_streak(habit['id'], conn)
            
            # Longest streak
            longest_streak = calculate_longest_streak(habit['id'], conn)
            
            # Completion rate (last 30 days)
            habit_completion = conn.execute('''
                SELECT 
                    COUNT(*) as total_entries,
                    SUM(CASE WHEN completed = 1 THEN 1 ELSE 0 END) as completed_entries
                FROM habit_entries
                WHERE habit_id = ? AND date >= ?
            ''', (habit['id'], thirty_days_ago)).fetchone()
            
            completion_rate = 0
            if habit_completion['total_entries'] > 0:
                completion_rate = round((habit_completion['completed_entries'] / habit_completion['total_entries']) * 100)
            
            habit_stats.append({
                'habit': habit,
                'current_streak': current_streak,
                'longest_streak': longest_streak,
                'completion_rate': completion_rate,
                'total_entries': habit_completion['total_entries']
            })
        
        # Generate personalized recommendations
        recommendations = generate_recommendations(user_id, conn)
        
        # Progress insights
        progress_insights = generate_progress_insights(user_id, conn)
        
        return render_template('analytics.html',
                             overall_completion_rate=overall_completion_rate,
                             best_day=best_day,
                             week_trend=week_trend,
                             this_week_rate=this_week_rate,
                             last_week_rate=last_week_rate,
                             habit_stats=habit_stats,
                             recommendations=recommendations,
                             progress_insights=progress_insights)
        
    except sqlite3.Error as e:
        flash('Error loading analytics.', 'error')
        print(f"Analytics error: {e}")
        return redirect(url_for('dashboard'))
    finally:
        conn.close()

def generate_recommendations(user_id, conn):
    """Generate personalized recommendations based on user data"""
    recommendations = []
    today = datetime.now().date()
    thirty_days_ago = today - timedelta(days=30)
    
    try:
        # Get habits with low completion rates
        low_performers = conn.execute('''
            SELECT h.name, h.category,
                   COUNT(he.id) as total_entries,
                   SUM(CASE WHEN he.completed = 1 THEN 1 ELSE 0 END) as completed_entries
            FROM habits h
            LEFT JOIN habit_entries he ON h.id = he.habit_id AND he.date >= ?
            WHERE h.user_id = ? AND h.active = 1
            GROUP BY h.id, h.name, h.category
            HAVING total_entries > 5
            ORDER BY (CAST(completed_entries AS FLOAT) / total_entries)
            LIMIT 2
        ''', (thirty_days_ago, user_id)).fetchall()
        
        for habit in low_performers:
            rate = round((habit['completed_entries'] / habit['total_entries']) * 100)
            if rate < 70:
                recommendations.append(f"Focus on '{habit['name']}' - only {rate}% completion rate. Try setting a specific time or linking it to an existing routine.")
        
        # Check for weekend vs weekday patterns
        weekend_performance = conn.execute('''
            SELECT 
                AVG(CASE WHEN CAST(strftime('%w', he.date) AS INTEGER) IN (0, 6) 
                    THEN CASE WHEN he.completed THEN 100.0 ELSE 0.0 END END) as weekend_rate,
                AVG(CASE WHEN CAST(strftime('%w', he.date) AS INTEGER) NOT IN (0, 6) 
                    THEN CASE WHEN he.completed THEN 100.0 ELSE 0.0 END END) as weekday_rate
            FROM habit_entries he
            JOIN habits h ON he.habit_id = h.id
            WHERE h.user_id = ? AND he.date >= ? AND h.active = 1
        ''', (user_id, thirty_days_ago)).fetchone()
        
        if weekend_performance['weekend_rate'] and weekend_performance['weekday_rate']:
            weekend_rate = round(weekend_performance['weekend_rate'])
            weekday_rate = round(weekend_performance['weekday_rate'])
            
            if weekday_rate - weekend_rate > 20:
                recommendations.append(f"Weekend performance ({weekend_rate}%) is much lower than weekdays ({weekday_rate}%). Consider adjusting weekend routines or setting reminders.")
            elif weekend_rate - weekday_rate > 20:
                recommendations.append(f"Great weekend consistency ({weekend_rate}%)! Try applying your weekend strategies to weekdays ({weekday_rate}%).")
        
        # Check for habits that haven't been tracked recently
        inactive_habits = conn.execute('''
            SELECT h.name, MAX(he.date) as last_entry
            FROM habits h
            LEFT JOIN habit_entries he ON h.id = he.habit_id
            WHERE h.user_id = ? AND h.active = 1
            GROUP BY h.id, h.name
            HAVING last_entry IS NULL OR last_entry < ?
        ''', (user_id, today - timedelta(days=3))).fetchall()
        
        if inactive_habits:
            habit_names = [h['name'] for h in inactive_habits[:2]]
            recommendations.append(f"Haven't tracked '{habit_names[0]}' recently. Consistency is key - even small steps count!")
        
        # Positive reinforcement for good streaks
        habits_for_streaks = conn.execute('''
            SELECT id, name FROM habits h
            WHERE h.user_id = ? AND h.active = 1
        ''', (user_id,)).fetchall()
        
        max_streak = 0
        best_habit = None
        for habit in habits_for_streaks:
            streak = calculate_current_streak(habit['id'], conn)
            if streak > max_streak:
                max_streak = streak
                best_habit = habit['name']
        
        if max_streak >= 7:
            recommendations.append(f"Excellent! You're on a {max_streak}-day streak with '{best_habit}'. Keep the momentum going!")
        
        # If no specific recommendations, provide general advice
        if not recommendations:
            recommendations.append("You're doing well overall! Try to maintain consistency and celebrate small wins.")
            recommendations.append("Consider adding a new habit that complements your existing ones.")
        
        return recommendations
        
    except sqlite3.Error as e:
        print(f"Recommendations error: {e}")
        return ["Unable to generate recommendations at this time."]

def generate_progress_insights(user_id, conn):
    """Generate progress insights"""
    insights = []
    today = datetime.now().date()
    
    try:
        # Compare first week vs recent week
        first_week_end = conn.execute('''
            SELECT MIN(date) as first_date FROM habit_entries he
            JOIN habits h ON he.habit_id = h.id
            WHERE h.user_id = ?
        ''', (user_id,)).fetchone()
        
        if first_week_end and first_week_end['first_date']:
            first_date = datetime.strptime(first_week_end['first_date'], '%Y-%m-%d').date()
            first_week_start = first_date + timedelta(days=7)
            
            if today > first_week_start:
                first_week_stats = conn.execute('''
                    SELECT 
                        COUNT(*) as total,
                        SUM(CASE WHEN completed = 1 THEN 1 ELSE 0 END) as completed
                    FROM habit_entries he
                    JOIN habits h ON he.habit_id = h.id
                    WHERE h.user_id = ? AND he.date BETWEEN ? AND ?
                ''', (user_id, first_date, first_week_start)).fetchone()
                
                recent_week_start = today - timedelta(days=7)
                recent_week_stats = conn.execute('''
                    SELECT 
                        COUNT(*) as total,
                        SUM(CASE WHEN completed = 1 THEN 1 ELSE 0 END) as completed
                    FROM habit_entries he
                    JOIN habits h ON he.habit_id = h.id
                    WHERE h.user_id = ? AND he.date >= ? AND h.active = 1
                ''', (user_id, recent_week_start)).fetchone()
                
                if first_week_stats['total'] > 0 and recent_week_stats['total'] > 0:
                    first_rate = round((first_week_stats['completed'] / first_week_stats['total']) * 100)
                    recent_rate = round((recent_week_stats['completed'] / recent_week_stats['total']) * 100)
                    
                    if recent_rate > first_rate:
                        insights.append(f"Great progress! Your completion rate improved from {first_rate}% in your first week to {recent_rate}% recently.")
                    elif recent_rate == first_rate:
                        insights.append(f"Consistent performance! You're maintaining a {recent_rate}% completion rate.")
                    else:
                        insights.append(f"Your completion rate was {first_rate}% initially and is {recent_rate}% recently. Consider what worked well in the beginning.")
        
        # Total habits completed insight
        total_completed = conn.execute('''
            SELECT COUNT(*) as total FROM habit_entries he
            JOIN habits h ON he.habit_id = h.id
            WHERE h.user_id = ? AND he.completed = 1
        ''', (user_id,)).fetchone()['total']
        
        if total_completed > 0:
            insights.append(f"You've completed {total_completed} habit tasks total - every completion builds momentum!")
        
        return insights
        
    except sqlite3.Error as e:
        print(f"Progress insights error: {e}")
        return ["Unable to generate insights at this time."]

if __name__ == '__main__':
    print("Starting Habit Tracker...")
    print("Database file:", DATABASE)
    
    # Get port from environment variable (Render provides this) or default to 5000
    import os
    port = int(os.environ.get('PORT', 5000))
    
    print(f"Access the app at: http://127.0.0.1:{port}")
    app.run(debug=False, host='0.0.0.0', port=port)
