# ------------------------------
# Think.4U - Charity Platform
# ------------------------------
from flask_mail import Mail, Message
import os
import io
from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify, send_file
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from supabase import create_client, Client
from supabase.lib.client_options import ClientOptions
from dotenv import load_dotenv
import razorpay
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timezone
import traceback
import tempfile
import qrcode
from io import BytesIO
import base64
from num2words import num2words
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from io import BytesIO
from PIL import Image, ImageDraw

# Load environment variables
load_dotenv()

# ------------------------------
# Flask App Configuration
# ------------------------------
app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'dev-secret-key-change-in-production')
UPI_VPA = os.getenv("UPI_VPA")

# ------------------------------
# Flask-Login Setup
# ------------------------------
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# ------------------------------
# Supabase Configuration
# ------------------------------
SUPABASE_URL = os.getenv('SUPABASE_URL')
SUPABASE_KEY = os.getenv('SUPABASE_KEY')

print(f"DEBUG SUPABASE_URL: {SUPABASE_URL}")
print(f"DEBUG SUPABASE_KEY set: {bool(SUPABASE_KEY)}")

options = ClientOptions()
options.auth = None

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# Test supabase connection
print(f"✅ Supabase initialized: {supabase is not None}")

# ------------------------------
# Razorpay Configuration
# ------------------------------
RAZOR_KEY = os.getenv('RAZOR_KEY_ID')
RAZOR_SECRET = os.getenv('RAZOR_KEY_SECRET')
razor_client = razorpay.Client(auth=(RAZOR_KEY, RAZOR_SECRET))

print(f"🔑 Razorpay initialized with key: {RAZOR_KEY[:15] if RAZOR_KEY else 'NOT SET'}...")

# ------------------------------
# Admin Credentials
# ------------------------------
app.config.update(
    MAIL_SERVER="smtp.gmail.com",
    MAIL_PORT=587,
    MAIL_USE_TLS=True,
    MAIL_USERNAME=os.getenv("MAIL_USERNAME"),
    MAIL_PASSWORD=os.getenv("MAIL_PASSWORD"),
    MAIL_DEFAULT_SENDER=("Think.4U", os.getenv("MAIL_USERNAME"))
)

mail = Mail(app)


# ------------------------------
# Upload Configuration
# ------------------------------
if os.environ.get("VERCEL" or "RENDER"):
    UPLOAD_FOLDER = tempfile.gettempdir()  # /tmp
else:
    UPLOAD_FOLDER = "static/uploads"
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024



def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# ------------------------------
# User Model for Flask-Login
# ------------------------------
class User(UserMixin):
    def __init__(self, id, email, name=None):
        self.id = id
        self.email = email
        self.name = name or 'User'
        self.username = name or email.split('@')[0]  # Extract username from email if no name
    
    def get_display_name(self):
        """Get user's display name"""
        return self.name or self.email
    
    def get_initials(self):
        """Get user's initials for avatar"""
        if self.name:
            parts = self.name.split()
            if len(parts) >= 2:
                return (parts[0][0] + parts[-1][0]).upper()
            return self.name[0].upper()
        return self.email[0].upper()


@login_manager.user_loader
def load_user(user_id):
    """Load user from Supabase"""
    try:
        print(f"🔍 Loading user ID: {user_id}")
        response = supabase.table('users').select('*').eq('id', int(user_id)).execute()
        if response.data:
            u = response.data[0]
            return User(id=u['id'], email=u['email'], name=u.get('name'))
        print(f"⚠️ No user found with ID: {user_id}")
        return None
    except Exception as e:
        print(f"❌ Error loading user from Supabase: {e}")
        import traceback
        traceback.print_exc()
        return None



@login_manager.unauthorized_handler
def unauthorized():
    flash("Please log in to access this page", "error")
    return redirect(url_for('login'))


# ===================================
# HELPER FUNCTIONS
# ===================================
def verify_checkout_signature(payload):
    """Verify Razorpay signature"""
    try:
        razor_client.utility.verify_payment_signature(payload)
        return True
    except razorpay.errors.SignatureVerificationError:
        return False

def send_email_async(subject, recipients, html):
    """Send email in background thread"""
    def send():
        try:
            with app.app_context():
                msg = Message(subject=subject, recipients=recipients, html=html)
                mail.send(msg)
                app.logger.info(f"Email sent to {recipients}")
        except Exception as e:
            app.logger.warning(f"Email failed: {e}")
    
    threading.Thread(target=send).start()

# ===================================
# PUBLIC ROUTES
# ===================================
@app.route("/")
def index():
    """Homepage with stats"""
    # Fetch programs
    try:
        response = supabase.table('programs').select('*').execute()
        programs = response.data if response.data else []
    except Exception as e:
        print(f"❌ Error fetching programs: {e}")
        programs = []
    
    # Calculate stats
    stats = {
        'total_donations': 0,
        'total_volunteers': 0,
        'total_programs': len(programs)
    }
    
    # Get donation count
    try:
        donations_response = supabase.table('donations').select('*', count='exact').execute()
        stats['total_donations'] = donations_response.count if hasattr(donations_response, 'count') else len(donations_response.data)
    except Exception as e:
        print(f"⚠️ Error fetching donation count: {e}")
    
    # Get volunteer count
    try:
        volunteers_response = supabase.table('volunteers').select('*', count='exact').execute()
        stats['total_volunteers'] = volunteers_response.count if hasattr(volunteers_response, 'count') else len(volunteers_response.data)
    except Exception as e:
        print(f"⚠️ Error fetching volunteer count: {e}")
    
    return render_template("index.html", 
                         programs=programs, 
                         razor_key=RAZOR_KEY,
                         stats=stats)



@app.route("/donate")
def donate():
    """Donation page"""
    amount_rupees = request.args.get("amount", "")
    amount_paise = None
    if amount_rupees:
        try:
            amount_paise = int(float(amount_rupees) * 100)
        except:
            pass
    return render_template("donate.html", amount_display=amount_rupees, amount_paise=amount_paise, razor_key=RAZOR_KEY)

@app.route("/donate-upi")
def donate_upi():
    """UPI donation page"""
    amount = request.args.get('amount', '')
    return render_template("donate_upi.html", upi_vpa=UPI_VPA, amount=amount)

@app.route("/create-order", methods=["POST"])
def create_order():
    """Create Razorpay order"""
    data = request.get_json()
    if not data:
        return jsonify({"error": "No JSON data"}), 400

    amount = data.get("amount")
    name = data.get("name", "").strip()
    email = data.get("email", "").strip()
    phone = data.get("phone", "").strip()

    if not amount or amount <= 0:
        return jsonify({"error": "Invalid amount"}), 400

    if not name or not email or not phone:
        return jsonify({"error": "Missing donor details"}), 400

    # Receipt ID (timezone safe)
    receipt = f"rcpt_{int(datetime.now(timezone.utc).timestamp())}"

    try:
        # Create Razorpay order
        order = razor_client.order.create({
            "amount": amount,
            "currency": "INR",
            "receipt": receipt,
            "payment_capture": 1
        })

        # ✅ SAVE FULL DONOR DATA
        supabase.table("donations").insert({
            "name": name,
            "email": email,
            "phone": phone,
            "amount": amount,
            "razorpay_order_id": order["id"],
            "status": "pending",
            "created_at": datetime.now(timezone.utc).isoformat()
        }).execute()

        return jsonify({
            "id": order["id"],
            "amount": order["amount"],
            "currency": order["currency"],
            "key_id": RAZOR_KEY
        })

    except razorpay.errors.BadRequestError as e:
        app.logger.error(f"Razorpay error: {e}")
        return jsonify({"error": "Razorpay authentication failed"}), 500

    except Exception as e:
        app.logger.error(f"Order creation failed: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/payment-success", methods=["GET", "POST"])
def payment_success_redirect():
    """Handle payment success redirect"""
    payment_id = request.args.get('razorpay_payment_id')
    order_id = request.args.get('razorpay_order_id')
    signature = request.args.get('razorpay_signature')
    
    if not all([payment_id, order_id, signature]):
        flash('Invalid payment data', 'error')
        return redirect('/')
    
    # Verify signature
    payload = {
        'razorpay_order_id': order_id,
        'razorpay_payment_id': payment_id,
        'razorpay_signature': signature
    }
    
    try:
        razor_client.utility.verify_payment_signature(payload)
        print("✅ Payment signature verified!")
        
        # Update donation in Supabase
        response = supabase.table('donations') \
            .update({
                "razorpay_payment_id": payment_id,
                "razorpay_signature": signature,
                "status": "paid",
                "payment_method": "Razorpay"
            }) \
            .eq('razorpay_order_id', order_id) \
            .execute()
        
        if response.data:
            donation = response.data[0]
            flash('Thank you for your donation!', 'success')
            return redirect(url_for('donation_receipt', donation_id=donation['id']))
    except razorpay.errors.SignatureVerificationError:
        print("❌ Payment signature verification failed!")
        flash('Payment verification failed', 'error')
    except Exception as e:
        print(f"❌ Error: {e}")
        flash('Error processing payment', 'error')
    
    return redirect('/')

@app.route("/razorpay-webhook", methods=["POST"])
def razorpay_webhook():
    """Handle Razorpay webhook events"""
    webhook_secret = os.getenv("RAZORPAY_WEBHOOK_SECRET", "")
    webhook_signature = request.headers.get('X-Razorpay-Signature')
    webhook_body = request.get_data()
    
    try:
        # Verify webhook signature
        if webhook_secret:
            razor_client.utility.verify_webhook_signature(
                webhook_body.decode('utf-8'),
                webhook_signature,
                webhook_secret
            )
        
        # Parse event data
        event = request.json
        event_type = event.get('event')
        
        print(f"📨 Webhook received: {event_type}")
        
        if event_type == 'payment.captured':
            payment = event['payload']['payment']['entity']
            order_id = payment['order_id']
            payment_id = payment['id']
            
            # Update donation status
            supabase.table('donations') \
                .update({
                    "razorpay_payment_id": payment_id,
                    "status": "paid",
                    "payment_method": "Razorpay"
                }) \
                .eq('razorpay_order_id', order_id) \
                .execute()
            
            print(f"✅ Payment captured: {payment_id}")
        
        return jsonify({"status": "ok"}), 200
        
    except Exception as e:
        print(f"❌ Webhook error: {e}")
        return jsonify({"error": str(e)}), 400
    
@app.route("/upi-qr")
def upi_qr():
    """Generate UPI QR code"""
    try:
        amount = request.args.get('amount', '')
        
        # Build UPI payment string
        upi_string = f"upi://pay?pa={UPI_VPA}&pn=Think.4U"
        
        if amount:
            upi_string += f"&am={amount}"
        
        upi_string += "&cu=INR"
        
        # Generate QR code
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=4,
        )
        qr.add_data(upi_string)
        qr.make(fit=True)
        
        img = qr.make_image(fill_color="black", back_color="white")
        
        # Save to BytesIO
        img_io = io.BytesIO()
        img.save(img_io, 'PNG')
        img_io.seek(0)
        
        return send_file(img_io, mimetype='image/png')
        
    except Exception as e:
        app.logger.error(f"Error generating QR code: {e}")
        # Return a simple error image
        from PIL import Image, ImageDraw, ImageFont
        
        img = Image.new('RGB', (300, 300), color='white')
        d = ImageDraw.Draw(img)
        d.text((150, 150), "QR Error", fill='black', anchor="mm")
        
        img_io = io.BytesIO()
        img.save(img_io, 'PNG')
        img_io.seek(0)
        
        return send_file(img_io, mimetype='image/png')



@app.route("/donation-receipt/<int:donation_id>")
def donation_receipt(donation_id):
    try:
        response = supabase.table("donations").select("*").eq("id", donation_id).execute()

        if not response.data:
            flash("Donation not found", "error")
            return redirect("/donate")

        donation = response.data[0]

        if donation["status"] != "paid":
            flash("Payment not completed", "warning")
            return redirect("/donate")

        created_at = datetime.fromisoformat(
            donation["created_at"].replace("Z", "+00:00")
        )
        donation["created_at"] = created_at
        
        receipt_url = url_for("donation_receipt", donation_id=donation_id, _external=True)
        qr_code = generate_qr(receipt_url)
        print("✅ QR length:", len(qr_code) if qr_code else "NO QR")

        # Shared context
        context = {
            "donation": donation,
            "amount": donation["amount"],
            "payment_method": donation.get("payment_method", "Online"),
            "qr_code": qr_code,
        }

        # 📧 SEND EMAIL (ONLY ONCE)
        if not donation.get("receipt_emailed"):
            email_html = render_template(
            "emails/donation_receipt_email.html",
            donation=donation,
            amount=donation["amount"]
        )

        msg = Message(
            subject="Thank you for your donation – Think.4U (80G Eligible)",
            recipients=[donation.get("email")]
        )
        msg.html = email_html

        try:
            mail.send(msg)
            supabase.table("donations").update(
                {"receipt_emailed": True}
            ).eq("id", donation_id).execute()
        except Exception as e:
            app.logger.error(f"❌ Email failed, but receipt shown: {e}")


        # 🌐 SHOW WEB RECEIPT
        return render_template(
            "emails/donation_receipt.html",
            **context
        )

    except Exception as e:
        traceback.print_exc()
        flash("Error loading receipt", "error")
        return redirect("/donate")


def generate_receipt_pdf(context):
    buffer = BytesIO()

    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=25*mm,
        leftMargin=25*mm,
        topMargin=25*mm,
        bottomMargin=25*mm
    )

    styles = getSampleStyleSheet()
    story = []

    story.append(Paragraph(f"<b>{context['org_name']}</b>", styles["Title"]))
    story.append(Spacer(1, 12))

    story.append(Paragraph(
        f"Donation Receipt<br/>"
        f"Receipt No: T4U-{context['donation']['id']}<br/>"
        f"Date: {context['created_at'].strftime('%d-%m-%Y')}",
        styles["Normal"]
    ))

    story.append(Spacer(1, 12))

    story.append(Paragraph(
        f"<b>Donor:</b> {context['donation'].get('name','Anonymous')}<br/>"
        f"<b>Email:</b> {context['donation'].get('email','N/A')}<br/>"
        f"<b>Amount:</b> ₹{context['amount']/100:.2f}",
        styles["Normal"]
    ))

    story.append(Spacer(1, 12))

    story.append(Paragraph(
        "This donation is eligible under Section 80G of the Income Tax Act, 1961.",
        styles["Normal"]
    ))

    story.append(Spacer(1, 12))

    story.append(Paragraph(
        f"80G Reg No: {context['org_80g']}<br/>PAN: {context['org_pan']}",
        styles["Normal"]
    ))

    doc.build(story)
    buffer.seek(0)
    return buffer.read()


@app.route("/volunteer", methods=["GET", "POST"])
def volunteer():
    """Volunteer registration"""
    if request.method == "POST":
        try:
            supabase.table('volunteers').insert({
                "name": request.form.get("name"),
                "email": request.form.get("email"),
                "phone": request.form.get("phone"),
                "message": request.form.get("message"),
                "status": "pending",
                "created_at": datetime.now(timezone.utc).isoformat()
            }).execute()
            
            flash("Thank you for volunteering! We'll be in touch soon.", "success")
            return redirect("/")
        except Exception as e:
            app.logger.error(f"Error creating volunteer: {e}")
            flash("Error submitting form. Please try again.", "error")
    
    return render_template("volunteer.html")

# ===================================
# AUTH ROUTES
# ===================================
@app.route("/login", methods=["GET", "POST"])
def login():
    """Admin login using Supabase"""
    if request.method == "POST":
        email = request.form.get("email")
        password = request.form.get("password")
        
        try:
            # Fetch user from Supabase
            response = supabase.table('users').select('*').eq('email', email).execute()
            
            if response.data and len(response.data) > 0:
                user_data = response.data[0]
                
                # Check password
                if check_password_hash(user_data.get('password_hash', ''), password):
                    # Create User object
                    user = User(
                        id=user_data['id'],
                        email=user_data['email'],
                        name=user_data.get('name', 'User'),
                    )
                    
                    # Login user
                    login_user(user)
                    flash("Logged in successfully!", "success")
                    
                    next_page = request.args.get('next')
                    return redirect(next_page or url_for('admin_dashboard'))
            
            flash("Invalid email or password", "error")
            
        except Exception as e:
            print(f"❌ Login error: {e}")
            import traceback
            traceback.print_exc()
            flash("Login error. Please try again.", "error")
    
    return render_template("login.html")

@app.route("/logout")
@login_required
def logout():
    """Logout"""
    logout_user()
    flash("Logged out successfully", "info")
    return redirect("/")

# ===================================
# ADMIN ROUTES
# ===================================
@app.route("/api/analytics")
@login_required
def api_analytics():
    """API endpoint for analytics"""
    try:
        # Get total donations
        donations_response = supabase.table('donations') \
            .select("amount", count='exact') \
            .eq('status', 'paid') \
            .execute()
        
        total_donations = sum(d['amount'] for d in donations_response.data) / 100 if donations_response.data else 0
        
        # Get counts
        volunteers_response = supabase.table('volunteers').select("*", count='exact').execute()
        programs_response = supabase.table('programs').select("*", count='exact').eq('status', 'active').execute()
        
        return jsonify({
            'total_donations': total_donations,
            'donation_count': donations_response.count or 0,
            'volunteer_count': volunteers_response.count or 0,
            'program_count': programs_response.count or 0
        })
    except Exception as e:
        app.logger.error(f"Analytics error: {e}")
        return jsonify({'error': str(e)}), 500
    
@app.route("/api/chart-donations")
@login_required
def chart_donations():
    """Get donation data for chart"""
    try:
        from datetime import datetime, timedelta
        
        # Get donations from last 7 days
        today = datetime.utcnow()
        days = []
        labels = []
        data = []
        
        for i in range(6, -1, -1):
            day = today - timedelta(days=i)
            days.append(day.date())
            labels.append(day.strftime('%a'))  # Mon, Tue, etc.
        
        # Get all paid donations
        response = supabase.table('donations') \
            .select("amount, created_at") \
            .eq('status', 'paid') \
            .execute()
        
        # Group by day
        day_totals = {day: 0 for day in days}
        
        for donation in response.data:
            created_date = datetime.fromisoformat(donation['created_at'].replace('Z', '+00:00')).date()
            if created_date in day_totals:
                day_totals[created_date] += donation['amount'] / 100  # Convert to rupees
        
        # Convert to list for chart
        data = [day_totals[day] for day in days]
        
        return jsonify({
            "labels": labels,
            "data": data
        })
    except Exception as e:
        app.logger.error(f"Chart donations error: {e}")
        # Return empty data instead of error
        return jsonify({
            "labels": ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'],
            "data": [0, 0, 0, 0, 0, 0, 0]
        })


@app.route("/api/chart-volunteers")
@login_required
def chart_volunteers():
    """Get volunteer status data for chart"""
    try:
        # Get volunteer counts by status
        response = supabase.table('volunteers').select("status").execute()
        
        statuses = {
            'approved': 0,
            'pending': 0,
            'rejected': 0
        }
        
        for volunteer in response.data:
            status = volunteer.get('status', 'pending').lower()
            if status in statuses:
                statuses[status] += 1
        
        return jsonify({
            "labels": ['Approved', 'Pending', 'Rejected'],
            "data": [statuses['approved'], statuses['pending'], statuses['rejected']]
        })
    except Exception as e:
        app.logger.error(f"Chart volunteers error: {e}")
        return jsonify({
            "labels": ['Approved', 'Pending', 'Rejected'],
            "data": [0, 0, 0]
        })


@app.route("/admin")
@login_required
def admin_dashboard():
    """Admin dashboard"""
    try:
        # Get recent donations
        donations_response = supabase.table('donations') \
            .select("*") \
            .eq('status', 'paid') \
            .order('created_at', desc=True) \
            .limit(10) \
            .execute()
        
        recent_donations = donations_response.data if donations_response.data else []
        
        # Calculate total
        total_donations = sum(d['amount'] for d in recent_donations) / 100
        
        volunteers_response = supabase.table('volunteers').select("*", count='exact').execute()
        
        return render_template(
            "admin/dashboard.html",
            total_donations=total_donations,
            donation_count=len(recent_donations),
            volunteer_count=volunteers_response.count or 0,
            recent_donations=recent_donations
        )
    except Exception as e:
        app.logger.error(f"Dashboard error: {e}")
        flash("Error loading dashboard", "error")
        return render_template("admin/dashboard.html", total_donations=0, donation_count=0, volunteer_count=0, recent_donations=[])

@app.route("/admin/donations")
@login_required
def admin_donations():
    """View all donations"""
    try:
        page = request.args.get('page', 1, type=int)
        per_page = 20
        offset = (page - 1) * per_page
        
        response = supabase.table('donations') \
            .select("*", count='exact') \
            .order('created_at', desc=True) \
            .range(offset, offset + per_page - 1) \
            .execute()
        
        # Mock pagination object
        class Pagination:
            def __init__(self, items, total, page, per_page):
                self.items = items
                self.total = total
                self.page = page
                self.per_page = per_page
                self.pages = (total + per_page - 1) // per_page
                self.has_prev = page > 1
                self.has_next = page < self.pages
                self.prev_num = page - 1 if self.has_prev else None
                self.next_num = page + 1 if self.has_next else None
        
        donations = Pagination(
            response.data if response.data else [],
            response.count or 0,
            page,
            per_page
        )
        
        return render_template("admin/donations.html", donations=donations)
    except Exception as e:
        app.logger.error(f"Donations page error: {e}")
        flash("Error loading donations", "error")
        return redirect('/admin')

@app.route("/admin/donations/export")
@login_required
def export_donations():
    """Export donations to CSV"""
    try:
        response = supabase.table('donations').select("*").eq('status', 'paid').execute()
        donations = response.data
        
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(['ID', 'Amount (₹)', 'Payment ID', 'Email', 'Date', 'Status'])
        
        for d in donations:
            writer.writerow([
                d['id'],
                f"{d['amount']/100:.2f}",
                d.get('razorpay_payment_id', ''),
                d.get('email', ''),
                d['created_at'],
                d['status']
            ])
        
        output.seek(0)
        return send_file(
            io.BytesIO(output.getvalue().encode('utf-8')),
            mimetype='text/csv',
            as_attachment=True,
            download_name=f'donations_{datetime.now().strftime("%Y%m%d")}.csv'
        )
    except Exception as e:
        flash(f"Export failed: {str(e)}", "error")
        return redirect('/admin/donations')





@app.route("/admin/volunteers")
@login_required
def admin_volunteers():
    """View all volunteers"""
    try:
        page = request.args.get('page', 1, type=int)
        per_page = 20
        offset = (page - 1) * per_page
        
        response = supabase.table('volunteers') \
            .select("*", count='exact') \
            .order('created_at', desc=True) \
            .range(offset, offset + per_page - 1) \
            .execute()
        
        class Pagination:
            def __init__(self, items, total, page, per_page):
                self.items = items
                self.total = total
                self.page = page
                self.per_page = per_page
                self.pages = (total + per_page - 1) // per_page
                self.has_prev = page > 1
                self.has_next = page < self.pages
                self.prev_num = page - 1 if self.has_prev else None
                self.next_num = page + 1 if self.has_next else None
        
        volunteers = Pagination(
            response.data if response.data else [],
            response.count or 0,
            page,
            per_page
        )
        
        return render_template("admin/volunteers.html", volunteers=volunteers)
    except Exception as e:
        app.logger.error(f"Volunteers page error: {e}")
        flash("Error loading volunteers", "error")
        return redirect('/admin')
    
@app.route("/admin/volunteers/export")
@login_required
def export_volunteers():
    """Export volunteers to CSV"""
    try:
        response = supabase.table('volunteers').select("*").execute()
        volunteers = response.data
        
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(['ID', 'Name', 'Email', 'Phone', 'Status', 'Date'])
        
        for v in volunteers:
            writer.writerow([
                v['id'],
                v['name'],
                v.get('email', ''),
                v.get('phone', ''),
                v['status'],
                v['created_at']
            ])
        
        output.seek(0)
        return send_file(
            io.BytesIO(output.getvalue().encode('utf-8')),
            mimetype='text/csv',
            as_attachment=True,
            download_name=f'volunteers_{datetime.now().strftime("%Y%m%d")}.csv'
        )
    except Exception as e:
        flash(f"Export failed: {str(e)}", "error")
        return redirect('/admin/volunteers')

@app.route("/admin/volunteer/<int:vid>/action", methods=["POST"])
@login_required
def volunteer_action(vid):
    """Update volunteer status"""
    action = request.form.get("action")
    
    try:
        status = "approved" if action == "approve" else "rejected"
        
        response = supabase.table('volunteers') \
            .update({"status": status}) \
            .eq('id', vid) \
            .execute()
        
        if response.data:
            volunteer = response.data[0]
            flash(f"Volunteer {volunteer['name']} {status}!", "success")
        
    except Exception as e:
        flash(f"Action failed: {str(e)}", "error")
    
    return redirect(url_for("admin_volunteers"))

# ===================================
# VOLUNTEER INFO ROUTE
# ===================================
@app.route("/admin/volunteer/<int:vid>/info")
@login_required
def volunteer_info(vid):
    """Get volunteer information as JSON"""
    try:
        response = supabase.table('volunteers').select('*').eq('id', vid).execute()
        
        if not response.data:
            return jsonify({"error": "Volunteer not found"}), 404
        
        return jsonify({"volunteer": response.data[0]})
    except Exception as e:
        app.logger.error(f"Error fetching volunteer info: {e}")
        return jsonify({"error": str(e)}), 500


# ===================================
# VOLUNTEER DONATIONS ROUTE
# ===================================
@app.route("/admin/volunteer/<int:vid>/donations")
@login_required
def volunteer_donations(vid):
    """View donations made by a volunteer"""
    try:
        # Get volunteer info
        volunteer_response = supabase.table('volunteers').select('*').eq('id', vid).execute()
        
        if not volunteer_response.data:
            flash('Volunteer not found', 'error')
            return redirect('/admin/volunteers')
        
        volunteer = volunteer_response.data[0]
        
        # Get donations by matching email
        donations_response = supabase.table('donations') \
            .select('*') \
            .eq('email', volunteer['email']) \
            .order('created_at', desc=True) \
            .execute()
        
        donations = donations_response.data if donations_response.data else []
        
        # Calculate total donated
        total_donated = sum(d.get('amount', 0) for d in donations) / 100  # Convert paise to rupees
        
        return render_template('admin/volunteer_donations.html',
                             volunteer=volunteer,
                             donations=donations,
                             total_donated=total_donated)
    except Exception as e:
        app.logger.error(f"Error fetching volunteer donations: {e}")
        flash('Error loading donations', 'error')
        return redirect('/admin/volunteers')


# ===================================
# DELETE VOLUNTEER ROUTE
# ===================================
@app.route("/admin/volunteer/<int:vid>/delete", methods=["DELETE"])
@login_required
def delete_volunteer(vid):
    """Delete a volunteer"""
    try:
        # Check if volunteer exists
        check_response = supabase.table('volunteers').select('id').eq('id', vid).execute()
        
        if not check_response.data:
            return jsonify({"error": "Volunteer not found"}), 404
        
        # Delete volunteer
        supabase.table('volunteers').delete().eq('id', vid).execute()
        
        print(f"✅ Volunteer {vid} deleted")
        
        return jsonify({"success": True, "message": "Volunteer removed successfully"})
    except Exception as e:
        app.logger.error(f"Error deleting volunteer: {e}")
        return jsonify({"error": str(e)}), 500


    

# ===================================
# PROGRAMS ROUTES (Supabase)
# ===================================

@app.route("/program/<int:program_id>")
def program_detail(program_id):
    """Display program details from Supabase"""
    try:
        response = supabase.table('programs').select('*').eq('id', program_id).execute()
        
        if not response.data:
            flash('Program not found', 'error')
            return redirect(url_for('index'))
        
        program = response.data[0]
        return render_template("program_detail.html", program=program)
    except Exception as e:
        app.logger.error(f"Error fetching program: {e}")
        flash('Error loading program', 'error')
        return redirect(url_for('index'))


@app.route("/admin/programs", methods=["GET", "POST"])
@login_required
def admin_programs():
    """Manage programs - supports URL and file upload to Supabase Storage"""
    
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        description = request.form.get("description", "").strip()
        image_url = request.form.get("image_url", "").strip()
        image_file = request.files.get("image")
        
        # Validation
        if not title or not description:
            flash("Title and description are required", "error")
            return redirect(url_for('admin_programs'))
        
        try:
            final_image_url = None
            
            # Handle file upload to Supabase Storage
            if image_file and image_file.filename:
                # Check file extension
                ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
                filename = image_file.filename
                
                if '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS:
                    # Generate unique filename
                    from werkzeug.utils import secure_filename
                    safe_filename = secure_filename(filename)
                    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                    name, ext = os.path.splitext(safe_filename)
                    unique_filename = f"programs/{name}_{timestamp}{ext}"
                    
                    # Upload to Supabase Storage
                    try:
                        file_data = image_file.read()
                        
                        # Check if bucket exists, if not try to create it
                        try:
                            # Try to list files in bucket (tests if it exists)
                            supabase.storage.from_('program-images').list()
                            print("✅ Bucket 'program-images' exists")
                        except Exception as bucket_error:
                            print(f"⚠️ Bucket doesn't exist, trying to create: {bucket_error}")
                            try:
                                # Create bucket
                                supabase.storage.create_bucket('program-images', options={'public': True})
                                print("✅ Created bucket 'program-images'")
                            except Exception as create_error:
                                print(f"❌ Could not create bucket: {create_error}")
                                flash("Storage bucket not found. Please create 'program-images' bucket in Supabase Storage.", "error")
                                return redirect(url_for('admin_programs'))
                        
                        # Upload file
                        upload_response = supabase.storage.from_('program-images').upload(
                            unique_filename,
                            file_data,
                            file_options={"content-type": image_file.content_type}
                        )
                        
                        # Get public URL
                        final_image_url = supabase.storage.from_('program-images').get_public_url(unique_filename)
                        print(f"✅ Image uploaded to Supabase Storage: {final_image_url}")
                        
                    except Exception as storage_error:
                        print(f"❌ Supabase storage error: {storage_error}")
                        flash(f"Error uploading image: {str(storage_error)}", "error")
                        return redirect(url_for('admin_programs'))
                else:
                    flash("Invalid file type. Use PNG, JPG, JPEG, GIF, or WEBP", "error")
                    return redirect(url_for('admin_programs'))
            
            # Use image URL if no file uploaded
            elif image_url:
                final_image_url = image_url
            
            # Insert into Supabase database
            program_data = {
                "title": title,
                "description": description,
                "image_url": final_image_url,
                "created_at": datetime.now(timezone.utc).isoformat()
            }
            
            response = supabase.table('programs').insert(program_data).execute()
            
            if response.data:
                print(f"✅ Program created: {title}")
                flash("Program created successfully!", "success")
            else:
                flash("Error: No data returned from Supabase", "error")
            
            return redirect(url_for('admin_programs'))
            
        except Exception as e:
            print(f"❌ Error creating program: {e}")
            import traceback
            traceback.print_exc()
            flash(f'Error creating program: {str(e)}', 'error')
    
    # GET request - Fetch all programs
    try:
        response = supabase.table('programs').select('*').order('created_at', desc=True).execute()
        programs = response.data if response.data else []
        print(f"✅ Loaded {len(programs)} programs")
    except Exception as e:
        print(f"❌ Error fetching programs: {e}")
        programs = []
        flash('Error loading programs', 'error')
    
    return render_template("admin/programs.html", programs=programs)







@app.route("/admin/programs/edit/<int:pid>", methods=["GET", "POST"])
@login_required
def admin_program_edit(pid):
    """Edit program in Supabase"""
    if not current_user.is_admin:
        return redirect(url_for('index'))

    # Fetch program
    try:
        response = supabase.table('programs').select('*').eq('id', pid).execute()
        
        if not response.data:
            flash('Program not found', 'error')
            return redirect(url_for('admin_programs'))
        
        program = response.data[0]
    except Exception as e:
        app.logger.error(f"Error fetching program: {e}")
        flash('Error loading program', 'error')
        return redirect(url_for('admin_programs'))

    if request.method == "POST":
        title = request.form.get("title")
        description = request.form.get("description")
        image_url = request.form.get("image_url")
        
        try:
            # Update in Supabase
            supabase.table('programs').update({
                "title": title,
                "description": description,
                "image_url": image_url,
                "updated_at": datetime.now(timezone.utc).isoformat()
            }).eq('id', pid).execute()
            
            flash("Program updated successfully!", "success")
            return redirect(url_for("admin_programs"))
        except Exception as e:
            app.logger.error(f"Error updating program: {e}")
            flash(f'Error updating program: {str(e)}', 'error')

    return render_template("admin/program_edit.html", program=program)


@app.route("/admin/program/<int:pid>/delete", methods=["POST", "DELETE"])
@login_required
def admin_program_delete(pid):
    """Delete program from Supabase"""

    
    try:
        supabase.table('programs').delete().eq('id', pid).execute()
        flash("Program deleted successfully!", "success")
    except Exception as e:
        app.logger.error(f"Error deleting program: {e}")
        flash(f'Error deleting program: {str(e)}', 'error')
    
    return redirect(url_for('admin_programs'))



# ------------------------------
# CMS Content Management Routes
# ------------------------------

@app.route("/admin/cms", methods=["GET", "POST"])
@login_required
def admin_cms():
    """Manage website content"""

    
    if request.method == "POST":
        content_id = request.form.get("content_id")
        key = request.form.get("key", "").strip()
        value = request.form.get("value", "").strip()
        
        if not key or not value:
            flash("Key and value are required", "error")
            return redirect(url_for('admin_cms'))
        
        try:
            if content_id:  # Update existing
                response = supabase.table('cms_content').update({
                "key": key,
                "value": value
                }).eq('id', int(content_id)).execute()
                flash("Content updated successfully!", "success")
            else:  # Create new
                response = supabase.table('cms_content').insert({
                "key": key,
                "value": value
                }).execute()
                flash("Content added successfully!", "success")
            
            return redirect(url_for('admin_cms'))
        except Exception as e:
            print(f"❌ Error saving content: {e}")
            flash(f"Error: {str(e)}", "error")
    
    # GET - Fetch all content
    try:
        response = supabase.table('cms_content').select('*').order('created_at', desc=True).execute()
        content_items = response.data if response.data else []
    except Exception as e:
        print(f"❌ Error fetching content: {e}")
        content_items = []
        flash("Error loading content", "error")
    
    return render_template("admin/cms.html", content_items=content_items)


@app.route("/admin/cms/delete/<int:content_id>", methods=["DELETE"])
@login_required
def admin_cms_delete(content_id):
    """Delete CMS content"""
    
    try:
        supabase.table('cms_content').delete().eq('id', content_id).execute()
        return jsonify({"success": True})
    except Exception as e:
        print(f"❌ Error deleting content: {e}")
        return jsonify({"error": str(e)}), 500
    
# ------------------------------
# CMS Helper Function
# ------------------------------

def get_cms_content(key, default=""):
    """Get CMS content by key"""
    try:
        response = supabase.table('cms_content').select('value').eq('key', key).execute()
        if response.data and len(response.data) > 0:
            return response.data[0]['value']
    except Exception as e:
        print(f"⚠️ Error fetching CMS content '{key}': {e}")
    return default


# Make CMS helper available in all templates
@app.context_processor
def inject_cms():
    """Inject CMS helper and other utilities into templates"""
    return dict(get_cms=get_cms_content)



@app.route("/admin/settings", methods=["GET", "POST"])
def admin_settings():
    """Admin settings page"""
    
    if request.method == "POST":
        form_type = request.form.get('form_type')
        
        try:
            if form_type == 'organization':
                # Save organization settings to CMS
                org_data = {
                    'org_name': request.form.get('org_name'),
                    'reg_number': request.form.get('reg_number'),
                    'tax_id': request.form.get('tax_id'),
                    'cert_80g': request.form.get('cert_80g')
                }
                
                for key, value in org_data.items():
                    supabase.table('cms_content').upsert({
                        'key': key,
                        'value': value
                    }).execute()
                
                flash('Organization information updated successfully!', 'success')
            
            elif form_type == 'contact':
                # Save contact settings
                contact_data = {
                    'contact_email': request.form.get('contact_email'),
                    'contact_phone': request.form.get('contact_phone'),
                    'contact_whatsapp': request.form.get('whatsapp'),
                    'contact_address': request.form.get('contact_address')
                }
                
                for key, value in contact_data.items():
                    supabase.table('cms_content').upsert({
                        'key': key,
                        'value': value
                    }).execute()
                
                flash('Contact information updated successfully!', 'success')
            
            elif form_type == 'payment':
                # Save payment settings
                payment_data = {
                    'razorpay_key': request.form.get('razorpay_key'),
                    'razorpay_secret': request.form.get('razorpay_secret'),
                    'upi_id': request.form.get('upi_id')
                }
                
                for key, value in payment_data.items():
                    if value:  # Only save if provided
                        supabase.table('cms_content').upsert({
                            'key': key,
                            'value': value
                        }).execute()
                
                flash('Payment settings updated successfully!', 'success')
            
            elif form_type == 'social':
                # Save social media links
                social_data = {
                    'social_facebook': request.form.get('facebook'),
                    'social_twitter': request.form.get('twitter'),
                    'social_instagram': request.form.get('instagram'),
                    'social_linkedin': request.form.get('linkedin')
                }
                
                for key, value in social_data.items():
                    supabase.table('cms_content').upsert({
                        'key': key,
                        'value': value
                    }).execute()
                
                flash('Social media links updated successfully!', 'success')
            
            elif form_type == 'password':
                # Change password
                current_password = request.form.get('current_password')
                new_password = request.form.get('new_password')
                confirm_password = request.form.get('confirm_password')
                
                # Verify current password
                admin_username = os.getenv('ADMIN_USERNAME', 'admin')
                admin_password = os.getenv('ADMIN_PASSWORD', 'admin123')
                
                if current_password != admin_password:
                    flash('Current password is incorrect!', 'error')
                elif new_password != confirm_password:
                    flash('New passwords do not match!', 'error')
                elif len(new_password) < 6:
                    flash('Password must be at least 6 characters!', 'error')
                else:
                    # Save new password to CMS (you should use environment variables in production)
                    supabase.table('cms_content').upsert({
                        'key': 'admin_password',
                        'value': new_password
                    }).execute()
                    flash('Password changed successfully! Please update your .env file.', 'success')
            
        except Exception as e:
            print(f"Error saving settings: {e}")
            flash(f'Error updating settings: {str(e)}', 'error')
        
        return redirect(url_for('admin_settings'))
    
    # GET request - Load settings
    try:
        # Fetch all settings from CMS
        response = supabase.table('cms_content').select('*').execute()
        settings_dict = {item['key']: item['value'] for item in response.data} if response.data else {}
        
        # Organize settings
        org_settings = {
            'name': settings_dict.get('org_name', ''),
            'reg_number': settings_dict.get('reg_number', ''),
            'tax_id': settings_dict.get('tax_id', ''),
            'cert_80g': settings_dict.get('cert_80g', '')
        }
        
        contact_settings = {
            'email': settings_dict.get('contact_email', ''),
            'phone': settings_dict.get('contact_phone', ''),
            'whatsapp': settings_dict.get('contact_whatsapp', ''),
            'address': settings_dict.get('contact_address', '')
        }
        
        payment_settings = {
            'razorpay_key': settings_dict.get('razorpay_key', ''),
            'razorpay_secret': settings_dict.get('razorpay_secret', ''),
            'upi_id': settings_dict.get('upi_id', '')
        }
        
        social_settings = {
            'facebook': settings_dict.get('social_facebook', ''),
            'twitter': settings_dict.get('social_twitter', ''),
            'instagram': settings_dict.get('social_instagram', ''),
            'linkedin': settings_dict.get('social_linkedin', '')
        }
        
    except Exception as e:
        print(f"Error loading settings: {e}")
        org_settings = {}
        contact_settings = {}
        payment_settings = {}
        social_settings = {}
    
    return render_template("admin/settings.html",
                         org_settings=org_settings,
                         contact_settings=contact_settings,
                         payment_settings=payment_settings,
                         social_settings=social_settings)

def generate_qr(data):
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=6,
        border=2,
    )
    qr.add_data(data)
    qr.make(fit=True)

    img = qr.make_image(fill_color="black", back_color="white")

    buf = BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)

    return base64.b64encode(buf.read()).decode("utf-8")


@app.route("/create-admin-secret-123")
def create_admin_secret():
    """Create admin user in Supabase - REMOVE AFTER USE!"""
    try:
        from datetime import datetime, timezone
        
        email = "admin@think4u.local"
        password = "adminpass"
        password_hash = generate_password_hash(password)
        
        # Check if admin exists
        response = supabase.table('users').select('*').eq('email', email).execute()
        
        if response.data:
            # Update existing user
            result = supabase.table('users').update({
                'password_hash': password_hash,
                'is_admin': True
            }).eq('email', email).execute()
            message = "✅ Admin user UPDATED!"
        else:
            # Create new admin user
            result = supabase.table('users').insert({
                'email': email,
                'password_hash': password_hash,
                'is_admin': True,
                'created_at': datetime.now(timezone.utc).isoformat()
            }).execute()
            message = "✅ Admin user CREATED!"
        
        return f"""
        <html>
        <body style="font-family: Arial; padding: 50px; background: #f0f9ff;">
            <div style="background: white; padding: 30px; border-radius: 15px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); max-width: 500px; margin: 0 auto;">
                <h1 style="color: #10b981;">🎉 {message}</h1>
                <p><strong>Email:</strong> {email}</p>
                <p><strong>Password:</strong> {password}</p>
                <hr>
                <p style="color: #666; font-size: 14px;">
                    ⚠️ <strong>Important:</strong> Delete this route from app.py after use!
                </p>
                <a href="/login" style="display: inline-block; margin-top: 20px; padding: 10px 20px; background: #10b981; color: white; text-decoration: none; border-radius: 8px;">
                    Go to Login →
                </a>
            </div>
        </body>
        </html>
        """
            
    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        return f"""
        <html>
        <body style="font-family: monospace; padding: 50px; background: #fee;">
            <h1 style="color: red;">❌ Error Creating Admin</h1>
            <pre>{error_trace}</pre>
        </body>
        </html>
        """

def amount_to_words(amount):
    return num2words(amount, lang='en_IN').replace('-', ' ').title()

# ===================================
# RUN APP
# ===================================
if __name__ == "__main__":
    print("✅ App configured with Supabase!")
    app.run(debug=True, host="0.0.0.0", port=5000)
