from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime, timedelta
import os

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'your-secret-key-change-this-in-production')

# Supabase connection - get from environment variable
DATABASE_URL = os.environ.get('DATABASE_URL')

if not DATABASE_URL:
    print("❌ ERROR: DATABASE_URL environment variable not set!")
    print("Please set your Supabase connection string:")
    print("export DATABASE_URL='postgresql://postgres.xxxxx:[password]@aws-0-us-east-1.pooler.supabase.com:6543/postgres'")

def get_db_connection():
    """Create database connection to Supabase PostgreSQL"""
    if not DATABASE_URL:
        print("❌ No DATABASE_URL configured")
        return None
        
    try:
        conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
        return conn
    except Exception as e:
        print(f"❌ Database connection error: {e}")
        return None

def init_db():
    """Initialize database with tables"""
    conn = get_db_connection()
    if not conn:
        print("❌ Could not connect to database for initialization")
        return False
    
    try:
        cursor = conn.cursor()
        
        print("🔄 Creating database tables...")
        
        # Create users table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                username VARCHAR(255) UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Create habits table
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
        
        # Create habit_entries table
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
        
        conn.commit()
        print("✅ Database tables created successfully!")
        return True
        
    except Exception as e:
        print(f"❌ Database initialization error: {e}")
        return False
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
        cursor = conn.cursor()
        for name, description, category in sample_habits:
            cursor.execute(
                'INSERT INTO habits (user_id, name, description, category) VALUES (%s, %s, %s, %s)',
                (user_id, name, description, category)
            )
        conn.commit()
        print(f"✅ Sample habits created for user: {user_id}")
    except Exception as e:
        print(f"❌ Error creating sample habits: {e}")
    finally:
        conn.close()

# Initialize database on startup
print("🚀 Starting Habit Tracker with Supabase...")
if DATABASE_URL:
    print("✅ DATABASE_URL found, initializing database...")
    init_db()
else:
    print("❌ DATABASE_URL not found!")

@app.route('/')
def index():
    """Home page - redirect to dashboard if logged in"""
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    return render_template('index.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    """User registration"""
    print(f"🔍 Register route called - Method: {request.method}")
    
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        
        print(f"🔍 Registration attempt - Username: '{username}'")
        
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
            cursor = conn.cursor()
            
            # Check if username exists
            cursor.execute('SELECT id FROM users WHERE username = %s', (username,))
            user = cursor.fetchone()
            
            if user:
                print(f"❌ Username '{username}' already exists")
                flash('Username already exists!', 'error')
                return render_template('register.html')
            
            # Create new user
            password_hash = generate_password_hash(password)
            
            cursor.execute(
                'INSERT INTO users (username, password_hash) VALUES (%s, %s) RETURNING id',
                (username, password_hash)
            )
            result = cursor.fetchone()
            user_id = result['id'] if result else None
            conn.commit()
            
            if user_id:
                print(f"✅ User created successfully: {username} (ID: {user_id})")
                # Create sample habits for new user
                create_sample_habits(user_id)
                
                flash('Registration successful! Please log in.', 'success')
                return redirect(url_for('login'))
            else:
                print("❌ Registration failed: No user ID returned")
                flash('Registration failed. Please try again.', 'error')
                
        except Exception as e:
            print(f"❌ Registration error: {e}")
            flash('Registration failed. Please try again.', 'error')
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
            cursor = conn.cursor()
            cursor.execute(
                'SELECT id, username, password_hash FROM users WHERE username = %s',
                (username,)
            )
            user = cursor.fetchone()
            
            if user and check_password_hash(user['password_hash'], password):
                session['user_id'] = user['id']
                session['username'] = user['username']
                flash('Login successful!', 'success')
                return redirect(url_for('dashboard'))
            else:
                flash('Invalid username or password!', 'error')
                
        except Exception as e:
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
        cursor = conn.cursor()
        user_id = session['user_id']
        today = datetime.now().date()
        
        # Get total active habits
        cursor.execute(
            'SELECT COUNT(*) as count FROM habits WHERE user_id = %s AND active = true',
            (user_id,)
        )
        total_habits = cursor.fetchone()['count']
        
        # Get today's completed habits
        cursor.execute('''
            SELECT COUNT(*) as count FROM habit_entries he
            JOIN habits h ON he.habit_id = h.id
            WHERE h.user_id = %s AND he.date = %s AND he.completed = true AND h.active = true
        ''', (user_id, today))
        completed_today = cursor.fetchone()['count']
        
        # Calculate overall completion rate (last 30 days)
        thirty_days_ago = today - timedelta(days=30)
        cursor.execute('''
            SELECT 
                COUNT(*) as total_entries,
                SUM(CASE WHEN completed = true THEN 1 ELSE 0 END) as completed_entries
            FROM habit_entries he
            JOIN habits h ON he.habit_id = h.id
            WHERE h.user_id = %s AND he.date >= %s AND h.active = true
        ''', (user_id, thirty_days_ago))
        completion_stats = cursor.fetchone()
        
        completion_rate = 0
        if completion_stats['total_entries'] > 0:
            completion_rate = round((completion_stats['completed_entries'] / completion_stats['total_entries']) * 100)
        
        # Count habits with active streaks (current streaks > 0)
        cursor.execute('''
            SELECT id, name FROM habits 
            WHERE user_id = %s AND active = true
        ''', (user_id,))
        habits = cursor.fetchall()
        
        active_streaks = 0
        for habit in habits:
            streak = calculate_current_streak(habit['id'], conn)
            if streak > 0:
                active_streaks += 1
        
        # Get recent activity (last 7 days)
        week_ago = today - timedelta(days=7)
        cursor.execute('''
            SELECT he.date, he.completed, h.name as habit_name
            FROM habit_entries he
            JOIN habits h ON he.habit_id = h.id
            WHERE h.user_id = %s AND he.date >= %s AND h.active = true
            ORDER BY he.date DESC, h.name
        ''', (user_id, week_ago))
        recent_entries = cursor.fetchall()
        
        return render_template('dashboard.html',
                             total_habits=total_habits,
                             completed_today=completed_today,
                             completion_rate=completion_rate,
                             active_streaks=active_streaks,
                             recent_entries=recent_entries,
                             today_str=today.strftime('%Y-%m-%d'))
        
    except Exception as e:
        flash('Error loading dashboard.', 'error')
        print(f"Dashboard error: {e}")
        return redirect(url_for('index'))
    finally:
        conn.close()

@app.route('/habits')
def habits():
    """Manage habits page"""
    print("🔍 HABITS ROUTE: Starting...")
    
    if 'user_id' not in session:
        print("❌ HABITS ROUTE: No user_id in session")
        return redirect(url_for('login'))
    
    print(f"✅ HABITS ROUTE: User ID {session['user_id']} found in session")
    
    conn = get_db_connection()
    if not conn:
        print("❌ HABITS ROUTE: Database connection failed")
        flash('Database error.', 'error')
        return redirect(url_for('dashboard'))
    
    print("✅ HABITS ROUTE: Database connection successful")
    
    try:
        cursor = conn.cursor()
        user_id = session['user_id']
        
        print(f"🔍 HABITS ROUTE: Executing query for user {user_id}")
        
        cursor.execute('''
            SELECT id, name, description, category, active, created_at
            FROM habits 
            WHERE user_id = %s 
            ORDER BY 
                CASE category 
                    WHEN 'Health' THEN 1
                    WHEN 'Fitness' THEN 2
                    WHEN 'Learning' THEN 3
                    WHEN 'Wellness' THEN 4
                    WHEN 'Personal' THEN 5
                    ELSE 6
                END, name
        ''', (user_id,))
        habits = cursor.fetchall()
        
        print(f"✅ HABITS ROUTE: Query successful, found {len(habits)} habits")
        print("🔍 HABITS ROUTE: Attempting to render template...")
        
        return render_template('habits.html', habits=habits)
        
    except Exception as e:
        print(f"❌ HABITS ROUTE: Exception occurred: {e}")
        flash('Error loading habits.', 'error')
        return redirect(url_for('dashboard'))
    finally:
        print("🔍 HABITS ROUTE: Closing database connection")
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
            cursor = conn.cursor()
            cursor.execute(
                'INSERT INTO habits (user_id, name, description, category) VALUES (%s, %s, %s, %s)',
                (session['user_id'], name, description, category)
            )
            conn.commit()
            flash('Habit added successfully!', 'success')
            return redirect(url_for('habits'))
            
        except Exception as e:
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
        cursor = conn.cursor()
        # Get habit details
        cursor.execute(
            'SELECT * FROM habits WHERE id = %s AND user_id = %s',
            (habit_id, session['user_id'])
        )
        habit = cursor.fetchone()
        
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
            
            cursor.execute('''
                UPDATE habits 
                SET name = %s, description = %s, category = %s, active = %s
                WHERE id = %s AND user_id = %s
            ''', (name, description, category, active, habit_id, session['user_id']))
            conn.commit()
            
            flash('Habit updated successfully!', 'success')
            return redirect(url_for('habits'))
        
        return render_template('edit_habit.html', habit=habit)
        
    except Exception as e:
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
        cursor = conn.cursor()
        user_id = session['user_id']
        
        # Get active habits in the same order as habits page
        cursor.execute('''
            SELECT id, name, category
            FROM habits 
            WHERE user_id = %s AND active = true
            ORDER BY 
                CASE category 
                    WHEN 'Health' THEN 1
                    WHEN 'Fitness' THEN 2
                    WHEN 'Learning' THEN 3
                    WHEN 'Wellness' THEN 4
                    WHEN 'Personal' THEN 5
                    ELSE 6
                END, name
        ''', (user_id,))
        habits = cursor.fetchall()
        
        # Get habit entries for the week
        cursor.execute('''
            SELECT habit_id, date, completed
            FROM habit_entries
            WHERE habit_id IN (SELECT id FROM habits WHERE user_id = %s AND active = true)
            AND date BETWEEN %s AND %s
        ''', (user_id, week_dates[0], week_dates[6]))
        entries = cursor.fetchall()
        
        # Organize entries by habit_id and date
        entries_dict = {}
        for entry in entries:
            if entry['habit_id'] not in entries_dict:
                entries_dict[entry['habit_id']] = {}
            entries_dict[entry['habit_id']][str(entry['date'])] = entry['completed']
        
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
        
    except Exception as e:
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
        
        try:
            cursor = conn.cursor()
            
            # Verify habit belongs to user
            cursor.execute(
                'SELECT id FROM habits WHERE id = %s AND user_id = %s AND active = true',
                (habit_id, session['user_id'])
            )
            habit = cursor.fetchone()
            
            if not habit:
                return jsonify({'success': False, 'error': 'Habit not found'})
            
            # Check current entry
            cursor.execute(
                'SELECT completed FROM habit_entries WHERE habit_id = %s AND date = %s',
                (habit_id, date_str)
            )
            current_entry = cursor.fetchone()
            
            if current_entry is None:
                # No entry exists, create as completed
                cursor.execute(
                    'INSERT INTO habit_entries (habit_id, date, completed) VALUES (%s, %s, %s)',
                    (habit_id, date_str, True)
                )
                new_status = 'completed'
            elif current_entry['completed']:
                # Currently completed, mark as not completed
                cursor.execute(
                    'UPDATE habit_entries SET completed = %s WHERE habit_id = %s AND date = %s',
                    (False, habit_id, date_str)
                )
                new_status = 'missed'
            else:
                # Currently not completed, delete entry (make it empty)
                cursor.execute(
                    'DELETE FROM habit_entries WHERE habit_id = %s AND date = %s',
                    (habit_id, date_str)
                )
                new_status = 'empty'
            
            conn.commit()
            return jsonify({'success': True, 'status': new_status})
            
        finally:
            conn.close()
        
    except (ValueError, KeyError, Exception) as e:
        print(f"Toggle habit error: {e}")
        return jsonify({'success': False, 'error': 'Server error'})

def calculate_current_streak(habit_id, conn):
    """Calculate current streak for a habit"""
    today = datetime.now().date()
    
    try:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT date, completed FROM habit_entries 
            WHERE habit_id = %s AND date <= %s
            ORDER BY date DESC
        ''', (habit_id, today))
        entries = cursor.fetchall()
        
        if not entries:
            return 0
        
        streak = 0
        current_date = today
        
        for entry in entries:
            entry_date = entry['date']
            
            if entry_date < current_date - timedelta(days=1):
                break
            
            if entry_date == current_date and entry['completed']:
                streak += 1
                current_date -= timedelta(days=1)
            elif entry_date == current_date and not entry['completed']:
                break
            elif entry_date < current_date:
                current_date = entry_date
                if entry['completed']:
                    streak += 1
                else:
                    break
        
        return streak
    except Exception as e:
        print(f"Calculate streak error: {e}")
        return 0

def calculate_longest_streak(habit_id, conn):
    """Calculate longest streak for a habit"""
    try:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT date, completed FROM habit_entries 
            WHERE habit_id = %s 
            ORDER BY date
        ''', (habit_id,))
        entries = cursor.fetchall()
        
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
    except Exception as e:
        print(f"Calculate longest streak error: {e}")
        return 0

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
        cursor = conn.cursor()
        user_id = session['user_id']
        today = datetime.now().date()
        thirty_days_ago = today - timedelta(days=30)
        seven_days_ago = today - timedelta(days=7)
        fourteen_days_ago = today - timedelta(days=14)
        
        # Overall completion rate (last 30 days)
        cursor.execute('''
            SELECT 
                COUNT(*) as total_entries,
                SUM(CASE WHEN completed = true THEN 1 ELSE 0 END) as completed_entries
            FROM habit_entries he
            JOIN habits h ON he.habit_id = h.id
            WHERE h.user_id = %s AND he.date >= %s AND h.active = true
        ''', (user_id, thirty_days_ago))
        completion_stats = cursor.fetchone()
        
        overall_completion_rate = 0
        if completion_stats['total_entries'] > 0:
            overall_completion_rate = round((completion_stats['completed_entries'] / completion_stats['total_entries']) * 100)
        
        # Best day of week analysis
        cursor.execute('''
            SELECT 
                CASE EXTRACT(DOW FROM he.date)
                    WHEN 0 THEN 'Sunday'
                    WHEN 1 THEN 'Monday'
                    WHEN 2 THEN 'Tuesday'
                    WHEN 3 THEN 'Wednesday'
                    WHEN 4 THEN 'Thursday'
                    WHEN 5 THEN 'Friday'
                    WHEN 6 THEN 'Saturday'
                END as day_name,
                COUNT(*) as total_entries,
                SUM(CASE WHEN completed = true THEN 1 ELSE 0 END) as completed_entries
            FROM habit_entries he
            JOIN habits h ON he.habit_id = h.id
            WHERE h.user_id = %s AND he.date >= %s AND h.active = true
            GROUP BY EXTRACT(DOW FROM he.date)
            HAVING COUNT(*) > 0
            ORDER BY (CAST(SUM(CASE WHEN completed = true THEN 1 ELSE 0 END) AS FLOAT) / COUNT(*)) DESC
        ''', (user_id, thirty_days_ago))
        day_stats = cursor.fetchall()
        
        best_day = None
        if day_stats:
            best_day = {
                'day': day_stats[0]['day_name'],
                'rate': round((day_stats[0]['completed_entries'] / day_stats[0]['total_entries']) * 100)
            }
        
        # Week comparison (this week vs last week)
        cursor.execute('''
            SELECT 
                COUNT(*) as total_entries,
                SUM(CASE WHEN completed = true THEN 1 ELSE 0 END) as completed_entries
            FROM habit_entries he
            JOIN habits h ON he.habit_id = h.id
            WHERE h.user_id = %s AND he.date >= %s AND h.active = true
        ''', (user_id, seven_days_ago))
        this_week_stats = cursor.fetchone()
        
        cursor.execute('''
            SELECT 
                COUNT(*) as total_entries,
                SUM(CASE WHEN completed = true THEN 1 ELSE 0 END) as completed_entries
            FROM habit_entries he
            JOIN habits h ON he.habit_id = h.id
            WHERE h.user_id = %s AND he.date >= %s AND he.date < %s AND h.active = true
        ''', (user_id, fourteen_days_ago, seven_days_ago))
        last_week_stats = cursor.fetchone()
        
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
        cursor.execute('''
            SELECT id, name, category
            FROM habits 
            WHERE user_id = %s AND active = true
            ORDER BY 
                CASE category 
                    WHEN 'Health' THEN 1
                    WHEN 'Fitness' THEN 2
                    WHEN 'Learning' THEN 3
                    WHEN 'Wellness' THEN 4
                    WHEN 'Personal' THEN 5
                    ELSE 6
                END, name
        ''', (user_id,))
        habits = cursor.fetchall()
        
        habit_stats = []
        for habit in habits:
            # Current streak
            current_streak = calculate_current_streak(habit['id'], conn)
            
            # Longest streak
            longest_streak = calculate_longest_streak(habit['id'], conn)
            
            # Completion rate (last 30 days)
            cursor.execute('''
                SELECT 
                    COUNT(*) as total_entries,
                    SUM(CASE WHEN completed = true THEN 1 ELSE 0 END) as completed_entries
                FROM habit_entries
                WHERE habit_id = %s AND date >= %s
            ''', (habit['id'], thirty_days_ago))
            habit_completion = cursor.fetchone()
            
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
        
    except Exception as e:
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
        cursor = conn.cursor()
        
        # Get habits with low completion rates
        cursor.execute('''
            SELECT h.name, h.category,
                   COUNT(he.id) as total_entries,
                   SUM(CASE WHEN he.completed = true THEN 1 ELSE 0 END) as completed_entries
            FROM habits h
            LEFT JOIN habit_entries he ON h.id = he.habit_id AND he.date >= %s
            WHERE h.user_id = %s AND h.active = true
            GROUP BY h.id, h.name, h.category
            HAVING COUNT(he.id) > 5
            ORDER BY (CAST(SUM(CASE WHEN he.completed = true THEN 1 ELSE 0 END) AS FLOAT) / COUNT(he.id))
            LIMIT 2
        ''', (thirty_days_ago, user_id))
        low_performers = cursor.fetchall()
        
        for habit in low_performers:
            rate = round((habit['completed_entries'] / habit['total_entries']) * 100)
            if rate < 70:
                recommendations.append(f"Focus on '{habit['name']}' - only {rate}% completion rate. Try setting a specific time or linking it to an existing routine.")
        
        # Check for weekend vs weekday patterns
        cursor.execute('''
            SELECT 
                AVG(CASE WHEN EXTRACT(DOW FROM he.date) IN (0, 6) 
                    THEN CASE WHEN he.completed THEN 100.0 ELSE 0.0 END END) as weekend_rate,
                AVG(CASE WHEN EXTRACT(DOW FROM he.date) NOT IN (0, 6) 
                    THEN CASE WHEN he.completed THEN 100.0 ELSE 0.0 END END) as weekday_rate
            FROM habit_entries he
            JOIN habits h ON he.habit_id = h.id
            WHERE h.user_id = %s AND he.date >= %s AND h.active = true
        ''', (user_id, thirty_days_ago))
        weekend_performance = cursor.fetchone()
        
        if weekend_performance['weekend_rate'] and weekend_performance['weekday_rate']:
            weekend_rate = round(weekend_performance['weekend_rate'])
            weekday_rate = round(weekend_performance['weekday_rate'])
            
            if weekday_rate - weekend_rate > 20:
                recommendations.append(f"Weekend performance ({weekend_rate}%) is much lower than weekdays ({weekday_rate}%). Consider adjusting weekend routines or setting reminders.")
            elif weekend_rate - weekday_rate > 20:
                recommendations.append(f"Great weekend consistency ({weekend_rate}%)! Try applying your weekend strategies to weekdays ({weekday_rate}%).")
        
        # Check for habits that haven't been tracked recently
        cursor.execute('''
            SELECT h.name, MAX(he.date) as last_entry
            FROM habits h
            LEFT JOIN habit_entries he ON h.id = he.habit_id
            WHERE h.user_id = %s AND h.active = true
            GROUP BY h.id, h.name
            HAVING MAX(he.date) IS NULL OR MAX(he.date) < %s
        ''', (user_id, today - timedelta(days=3)))
        inactive_habits = cursor.fetchall()
        
        if inactive_habits:
            habit_names = [h['name'] for h in inactive_habits[:2]]
            recommendations.append(f"Haven't tracked '{habit_names[0]}' recently. Consistency is key - even small steps count!")
        
        # Positive reinforcement for good streaks
        cursor.execute('''
            SELECT id, name FROM habits h
            WHERE h.user_id = %s AND h.active = true
        ''', (user_id,))
        habits_for_streaks = cursor.fetchall()
        
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
        
    except Exception as e:
        print(f"Recommendations error: {e}")
        return ["Unable to generate recommendations at this time."]

def generate_progress_insights(user_id, conn):
    """Generate progress insights"""
    insights = []
    today = datetime.now().date()
    
    try:
        cursor = conn.cursor()
        
        # Compare first week vs recent week
        cursor.execute('''
            SELECT MIN(date) as first_date FROM habit_entries he
            JOIN habits h ON he.habit_id = h.id
            WHERE h.user_id = %s
        ''', (user_id,))
        first_week_end = cursor.fetchone()
        
        if first_week_end and first_week_end['first_date']:
            first_date = first_week_end['first_date']
            first_week_start = first_date + timedelta(days=7)
            
            if today > first_week_start:
                cursor.execute('''
                    SELECT 
                        COUNT(*) as total,
                        SUM(CASE WHEN completed = true THEN 1 ELSE 0 END) as completed
                    FROM habit_entries he
                    JOIN habits h ON he.habit_id = h.id
                    WHERE h.user_id = %s AND he.date BETWEEN %s AND %s
                ''', (user_id, first_date, first_week_start))
                first_week_stats = cursor.fetchone()
                
                recent_week_start = today - timedelta(days=7)
                cursor.execute('''
                    SELECT 
                        COUNT(*) as total,
                        SUM(CASE WHEN completed = true THEN 1 ELSE 0 END) as completed
                    FROM habit_entries he
                    JOIN habits h ON he.habit_id = h.id
                    WHERE h.user_id = %s AND he.date >= %s AND h.active = true
                ''', (user_id, recent_week_start))
                recent_week_stats = cursor.fetchone()
                
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
        cursor.execute('''
            SELECT COUNT(*) as total FROM habit_entries he
            JOIN habits h ON he.habit_id = h.id
            WHERE h.user_id = %s AND he.completed = true
        ''', (user_id,))
        total_completed = cursor.fetchone()['total']
        
        if total_completed > 0:
            insights.append(f"You've completed {total_completed} habit tasks total - every completion builds momentum!")
        
        return insights
        
    except Exception as e:
        print(f"Progress insights error: {e}")
        return ["Unable to generate insights at this time."]

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    
    # Check if we're in production (Render sets this)
    is_production = os.environ.get('RENDER') or os.environ.get('RAILWAY_ENVIRONMENT')
    
    if DATABASE_URL:
        if is_production:
            print(f"✅ Starting production app on port {port} with Supabase database")
        else:
            print(f"✅ Starting development app on port {port} with Supabase database")
            print(f"🌐 Access the app at: http://127.0.0.1:{port}")
    else:
        print("❌ WARNING: No DATABASE_URL set!")
    
    # Production settings vs Development settings
    if is_production:
        app.run(debug=False, host='0.0.0.0', port=port)
    else:
        app.run(debug=True, host='127.0.0.1', port=port)
