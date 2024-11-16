from email.encoders import encode_base64
from email.mime.application import MIMEApplication

from flask import Flask, render_template, request, redirect, url_for, jsonify, send_file, session, flash
from flask_mail import Mail, Message
from app import app, db
from models import Product
from datetime import datetime
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import random
import qrcode
import os
import json
import secrets

# Secret key for session management
app.secret_key = secrets.token_hex(16)  # Generates a random 16-byte hexadecimal string

# Flask-Mail configuration for Gmail
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = 'project.spillbill@gmail.com'  # Replace with your email
app.config['MAIL_PASSWORD'] =   # Replace with your email password

mail = Mail(app)

# Home route
@app.route('/')
def home():
    return render_template('index.html')  # Main home page with Admin and Self Checkout options

# Inventory route
@app.route('/inventory')
def inventory():
    products = Product.query.all()
    return render_template('inventory.html', products=products)

# Route to add a new product
@app.route('/add_items', methods=['GET', 'POST'])
def add_items():
    if request.method == 'POST':
        name = request.form['name']
        price = request.form['price']
        try:
            price = float(price)  # Convert price to float
            new_product = Product(name=name, price=price)
            db.session.add(new_product)
            db.session.commit()
            # Generate QR code
            qr_content = f'Product: {name}, Price: {price:.2f}'
            qr = qrcode.make(qr_content)
            qr.save(f'static/qr_codes/{name}_qrcode.png')
            return redirect(url_for('inventory'))
        except Exception as e:
            flash(f"Error adding product: {e}", "danger")
            return redirect(url_for('add_items'))
    return render_template('add_items.html')

# Route to delete a product
@app.route('/delete_product/<int:id>', methods=['GET', 'POST'])
def delete_product(id):
    product = Product.query.get_or_404(id)
    if request.method == 'POST':
        try:
            qr_code_path = os.path.join('static', 'qr_codes', f'{product.name}_qrcode.png')
            if os.path.exists(qr_code_path):
                os.remove(qr_code_path)
            db.session.delete(product)
            db.session.commit()
            flash("Product deleted successfully", "success")
            return redirect(url_for('inventory'))
        except Exception as e:
            flash(f"Error deleting product: {e}", "danger")
            return redirect(url_for('inventory'))
    return render_template('delete_product.html', product=product)

# Route for customer details
@app.route('/customer_details', methods=['GET', 'POST'])
def customer_details():
    if request.method == 'POST':
        print("Received POST request")
        print(f"Request form data: {request.form}")  # Logs all received form data

        user_name = request.form.get('name')
        phone_number = request.form.get('phone')
        useremail = request.form.get('email')

        if not useremail:
            print("Email field is missing or empty!")  # Debugging message
            flash("Please enter a valid email address.", "danger")
            return redirect(url_for('customer_details'))

        print(f"Form data - Name: {user_name}, Phone: {phone_number}, Email: {useremail}")

        return redirect(url_for('scan_products', name=user_name, phone=phone_number, email=useremail))

    return render_template('customer_details.html')

# Route to scan products and add by name
@app.route('/scan_products', methods=['GET', 'POST'])
def scan_products():
    user_name = request.args.get('name')
    phone_number = request.args.get('phone')
    useremail = request.args.get('email')

    # Initialize session['scanned_products'] if it doesn't exist
    if 'scanned_products' not in session:
        session['scanned_products'] = []
        print("Session initialized with an empty product list.")

    if request.method == 'POST':
        product_name = request.form.get('product_name')

        if product_name:
            # Find product by name (case-insensitive)
            product = Product.query.filter(Product.name.ilike(product_name)).first()

            if product:
                # Update scanned_products list in the session
                existing_product = next((p for p in session['scanned_products'] if p['name'] == product.name), None)
                if existing_product:
                    existing_product['quantity'] += 1
                else:
                    session['scanned_products'].append({'name': product.name, 'price': product.price, 'quantity': 1})

                # Save session changes
                session.modified = True
                print("Session after adding product:", session)
                return redirect(url_for('scan_products', name=user_name, phone=phone_number, email=useremail))
            else:
                flash("Product not found in inventory", "danger")

    print(f"Scanned products in session: {session['scanned_products']}")  # Debugging statement
    return render_template('scan_products.html', name=user_name, phone=phone_number, email=useremail,
                           scanned_products=session['scanned_products'])

# Route to generate bill and send email to the user
@app.route('/generate_bill', methods=['POST'])
def generate_bill():
    # Retrieve scanned products from session
    if 'scanned_products' not in session or not session['scanned_products']:
        flash("No products scanned.", "danger")
        print("No products scanned in session.")
        return redirect(url_for('scan_products'))

    scanned_products = session['scanned_products']

    print("Generating Bill...")  # Debugging statement
    now = datetime.now()
    timestamp = now.strftime("%d-%m-%Y_%H-%M-%S")
    pdf_filename = f'bills/bill_{timestamp}.pdf'

    # Get form data
    user_name = request.form.get("name")
    phone_number = request.form.get("phone")
    useremail = request.form.get("email")

    print(f"Form data - Name: {user_name}, Phone: {phone_number}, Email: {useremail}")  # Debugging statement

    if not useremail:
        flash("Email is required.", "danger")
        return redirect(url_for('customer_details'))

    # Retrieve scanned products from global variable
    print(f"Scanned Products: {scanned_products}")  # Debugging statement

    if not scanned_products:
        flash("No products scanned.", "danger")
        return redirect(url_for('scan_products', name=user_name, phone=phone_number, email=useremail))

    # Bill generation logic
    subtotal = sum(product['price'] * product['quantity'] for product in scanned_products)
    cgst = subtotal * 0.025
    sgst = subtotal * 0.025
    grand_total = subtotal + cgst + sgst

    # Generate PDF
    c = canvas.Canvas(pdf_filename, pagesize=A4)
    width, height = A4
    c.setFont("Helvetica-Bold", 16)
    c.drawString(100, height - 80, f"SpillBILL - Customer Bill")
    c.setFont("Helvetica", 12)
    c.drawString(100, height - 110, f"Customer Name: {user_name}")
    c.drawString(100, height - 130, f"Phone: {phone_number}")
    c.drawString(100, height - 150, f"Date: {now.strftime('%d/%m/%Y')}")
    c.drawString(100, height - 170, f"Time: {now.strftime('%H:%M:%S')}")
    c.drawString(100, height - 190, f"Bill No.: {timestamp}")
    c.drawString(100, height - 210, f"Cashier: Your Cashier Name")
    c.drawString(100, height - 230, "Items Purchased:")

    # Add items to PDF
    y = height - 260
    for product in scanned_products:
        c.drawString(100, y, product['name'])
        c.drawString(250, y, str(product['quantity']))
        c.drawString(400, y, f"{product['price'] * product['quantity']:.2f}")
        y -= 20

    # Add totals
    c.setFont("Helvetica-Bold", 12)
    y -= 20
    c.drawString(100, y, f"Subtotal: ₹{subtotal:.2f}")
    y -= 20
    c.drawString(100, y, f"CGST (2.5%): ₹{cgst:.2f}")
    y -= 20
    c.drawString(100, y, f"SGST (2.5%): ₹{sgst:.2f}")
    y -= 20
    c.drawString(100, y, f"Grand Total: ₹{grand_total:.2f}")

    c.save()

    # Send email with the bill attached
    try:
        msg = MIMEMultipart()
        msg['From'] = 'project.spillbill@gmail.com'
        msg['To'] = useremail
        msg['Subject'] = f'Your SpillBILL - Bill {timestamp}'

        body = f"Dear {user_name},\n\nThank you for shopping with us. Your bill is attached below."
        msg.attach(MIMEText(body, 'plain'))

        # Attach the PDF file
        with open(pdf_filename, "rb") as file:
            msg.attach(MIMEApplication(file.read(), _subtype="pdf", _encoder=encode_base64))

        # Send the email
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login('project.spillbill@gmail.com', 'mcda vjia mnmr vdgb')
        text = msg.as_string()
        server.sendmail('project.spillbill@gmail.com', useremail, text)
        server.quit()

        flash("Bill generated and emailed successfully.", "success")
    except Exception as e:
        flash(f"Error generating bill or sending email: {e}", "danger")

        # Clear scanned products after bill is generated
        session.pop('scanned_products', None)

    return redirect(url_for('home'))


# Function to send OTP to admin with error handling
def send_otp_email(adminemail, otp):
    try:
        msg = Message("Your OTP for SpillBILL Admin Login",
                      sender=app.config['MAIL_USERNAME'],
                      recipients=[adminemail])
        msg.body = f'Your OTP for admin login is {otp}.'
        mail.send(msg)
    except Exception as e:
        flash(f"Error sending OTP: {e}", "danger")

# Function to send bill email to the user with error handling
def send_bill_email(useremail, user_name, grand_total):
    try:
        msg = Message("Your SpillBILL Receipt",
                      sender=app.config['MAIL_USERNAME'],
                      recipients=[useremail])
        msg.body = f"Hello {user_name},\n\nThank you for shopping with us! Your total bill is ₹{grand_total:.2f}."
        mail.send(msg)
    except Exception as e:
        flash(f"Error sending bill email: {e}", "danger")

# API to fetch product list for adding by name
@app.route('/api/products')
def get_products():
    products = Product.query.all()
    return jsonify([{'name': product.name, 'price': product.price} for product in products])

# Ensure the bills directory exists
if not os.path.exists('bills'):
    os.makedirs('bills')


# Mails for Admin Login

pre_approved_emails = ["project.spillbill@gmail.com","manitjha032@gmail.com"]


# Admin login route
@app.route('/admin_login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        # Step 1: Handle email submission
        if 'email' in request.form and not session.get('otp'):
            email = request.form['email']
            if email in pre_approved_emails:
                otp = random.randint(100000, 999999)  # Generate a new OTP
                session['otp'] = str(otp)  # Store OTP in session (as string for comparison)
                session['email'] = email  # Store the email in the session
                session['otp_generated_at'] = datetime.now().isoformat()  # Track OTP generation time
                send_otp_email(email, otp)  # Send the OTP via email
                flash("OTP has been sent to your email.", "success")
                return render_template('admin_login.html', otp_sent=True)  # Show OTP input form
            else:
                flash("Unauthorized email address.", "danger")
                return redirect(url_for('admin_login'))

        # Step 2: Handle OTP verification
        elif 'otp' in request.form and session.get('otp'):
            entered_otp = request.form['otp']
            otp_generated_at = session.get('otp_generated_at')
            if otp_generated_at:
                # Check if OTP has expired (valid for 5 minutes)
                otp_age = (datetime.now() - datetime.fromisoformat(otp_generated_at)).total_seconds()
                if otp_age > 300:  # OTP expired after 5 minutes
                    flash("OTP has expired. Please request a new one.", "danger")
                    session.pop('otp', None)  # Clear expired OTP
                    session.pop('otp_generated_at', None)  # Clear OTP timestamp
                    return redirect(url_for('admin_login'))

            # Validate OTP
            if session['otp'] == entered_otp:
                session.pop('otp', None)  # Clear OTP after successful validation
                session.pop('otp_generated_at', None)  # Clear OTP timestamp
                session['admin_logged_in'] = True  # Mark the admin as logged in
                flash("Logged in successfully.", "success")
                return redirect(url_for('admin_dashboard'))
            else:
                flash("Invalid OTP. Please try again.", "danger")
                return render_template('admin_login.html', otp_sent=True)

        else:
            flash("Something went wrong. Please try again.", "danger")
            return redirect(url_for('admin_login'))

    return render_template('admin_login.html', otp_sent=False)


@app.route('/admin_dashboard')
def admin_dashboard():
    # Check if the user is logged in
    if 'admin_logged_in' in session:
        return render_template('admin_dashboard.html')
    else:
        return redirect(url_for('admin_login'))

@app.route('/')
def index():
    return render_template('index.html')


# Logout route
@app.route('/logout')
def logout():
    session.pop('admin_logged_in', None)  # Remove admin session
    session.pop('otp', None)  # Clear OTP session
    return redirect(url_for('index'))  # Redirect to home page (index.html)


@app.route('/test_session')
def test_session():
    # Set a value in the session
    session['scanned_products'] = [{'name': 'miLK', 'price': 50, 'quantity': 2}]

    # Print the session to see if the data persists
    print(f"Test Session: {session.get('scanned_products')}")

    return "Session Test Complete!"


if __name__ == '__main__':
    app.run(debug=True)
