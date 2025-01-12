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
app.config['MAIL_PASSWORD'] = 'mcda vjia mnmr vdgb'   # Replace with your email password
app.config['SESSION_TYPE'] = 'filesystem'
# Initialize extensions
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

# Routes for scanning products
@app.route('/scan_products', methods=['GET', 'POST'])
def scan_products():
    # Retrieve query parameters for customer details
    user_name = request.args.get('name')
    phone_number = request.args.get('phone')
    useremail = request.args.get('email')

    # Initialize scanned_products in session if not present
    session.setdefault('scanned_products', [])
    print("Session initialized with an empty product list.") if not session['scanned_products'] else None

    if request.method == 'POST':
        # Check if product_name field exists and is not empty
        if not request.form.get('product_name'):
            print("Error: No product name provided in the request.")
            flash("Product name is required to add an item.", "danger")
            return redirect(url_for('scan_products', name=user_name, phone=phone_number, email=useremail))

        product_name = request.form.get('product_name', '').strip()
        print(f"POST request received to add product: {product_name}")  # Debugging

        if product_name:
            # Search for product in the inventory, case-insensitive
            product = Product.query.filter(Product.name.ilike(product_name)).first()
            if product:
                # Update product quantity in the session or add a new product
                for scanned in session['scanned_products']:
                    if scanned['name'].lower() == product.name.lower():
                        scanned['quantity'] += 1
                        break
                else:
                    session['scanned_products'].append({
                        'name': product.name,
                        'price': product.price,
                        'quantity': 1
                    })
                session.modified = True  # Mark session as modified
                print(f"Product {product.name} added/updated in session.")
                return redirect(url_for('scan_products', name=user_name, phone=phone_number, email=useremail))
            else:
                flash("Product not found in inventory.", "danger")

    return render_template(
        'scan_products.html',
        name=user_name, phone=phone_number, email=useremail,
        scanned_products=session['scanned_products']
    )

# Routes to generate bill
@app.route('/generate_bill', methods=['POST'])
def generate_bill():
    print("Received POST request")
    print("Request form data:", request.form)

    # Check for 'products' field in the POST request
    products_json = request.form.get('products')
    if not products_json:
        print("Error: No products were provided in the request.")
        flash("No products were selected.", "danger")
        return redirect(url_for('scan_products'))

    # Deserialize the products
    try:
        scanned_products = json.loads(products_json)
        print(f"Deserialized products: {scanned_products}")
    except json.JSONDecodeError as e:
        print(f"Error decoding products JSON: {e}")
        flash("Invalid product data received.", "danger")
        return redirect(url_for('scan_products'))

    # Check if the deserialized list is empty
    if not scanned_products:
        print("Error: Empty product list received.")
        flash("No products were selected.", "danger")
        return redirect(url_for('scan_products'))

    # Retrieve form data
    user_name = request.form.get("name", "Customer")
    phone_number = request.form.get("phone", "Unknown")
    useremail = request.form.get("email", "").strip()

    # Ensure the email field is not empty
    if not useremail:
        flash("Email is required.", "danger")
        return redirect(url_for('customer_details'))

    # Calculate totals
    subtotal = sum(item['price'] * item['quantity'] for item in scanned_products)
    cgst = sgst = subtotal * 0.025  # 2.5% tax
    grand_total = subtotal + cgst + sgst

    # Generate bill filename
    now = datetime.now()
    timestamp = now.strftime("%d-%m-%Y_%H-%M-%S")
    pdf_filename = f'bills/bill_{timestamp}.pdf'

    # Create PDF
    try:
        c = canvas.Canvas(pdf_filename, pagesize=A4)
        width, height = A4
        c.setFont("Helvetica-Bold", 16)
        c.drawString(100, height - 80, "SpillBILL - Customer Bill")
        c.setFont("Helvetica", 12)
        c.drawString(100, height - 110, f"Customer Name: {user_name}")
        c.drawString(100, height - 130, f"Phone: {phone_number}")
        c.drawString(100, height - 150, f"Date: {now.strftime('%d/%m/%Y')}")
        c.drawString(100, height - 170, f"Time: {now.strftime('%H:%M:%S')}")
        c.drawString(100, height - 190, f"Bill No.: {timestamp}")
        c.drawString(100, height - 210, "Items Purchased:")

        # Populate product details in the PDF
        y = height - 240
        for product in scanned_products:
            c.drawString(100, y, product['name'])
            c.drawString(300, y, f"{product['quantity']}")
            c.drawString(450, y, f"₹{product['price'] * product['quantity']:.2f}")
            y -= 20
        c.drawString(100, y, f"Subtotal: ₹{subtotal:.2f}")
        c.drawString(100, y - 20, f"CGST (2.5%): ₹{cgst:.2f}")
        c.drawString(100, y - 40, f"SGST (2.5%): ₹{sgst:.2f}")
        c.drawString(100, y - 60, f"Grand Total: ₹{grand_total:.2f}")
        c.save()

        # Send email
        msg = MIMEMultipart()
        msg['From'] = 'project.spillbill@gmail.com'
        msg['To'] = useremail
        msg['Subject'] = f'SpillBILL - Your Bill {timestamp}'
        msg.attach(MIMEText(
            f"Dear {user_name},\n\nWe are pleased to provide you with your e-bill for your recent transactions with XYZ Store. Please find the attached document for detailed billing information."
            f"\n\nKindly review the e-bill at your earliest convenience. If you have any questions or require further assistance, our customer support team is available to help. \n\nWe value your business and appreciate your prompt attention to this matter. Thank you for choosing SpillBill.",
            'plain'))
        with open(pdf_filename, "rb") as pdf:
            msg.attach(MIMEApplication(pdf.read(), _subtype="pdf"))
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login('project.spillbill@gmail.com', 'mcda vjia mnmr vdgb')
        server.send_message(msg)
        server.quit()
        flash("Bill generated and sent successfully.", "success")
    except Exception as e:
        flash(f"Error generating bill or sending email: {e}", "danger")

    session.pop('scanned_products', None)  # Clear scanned products

    # Prepare data to pass to the template
    date = now.strftime('%d/%m/%Y')
    time = now.strftime('%H:%M:%S')
    bill_no = timestamp
    cashier = "Admin"  # You can replace this with actual admin name if needed

    # Return the rendered total_bill.html with all the necessary data
    return render_template(
        'total_bill.html',
        date=date,
        time=time,
        bill_no=bill_no,
        cashier=cashier,
        products=scanned_products,
        subtotal=subtotal,
        cgst=cgst,
        sgst=sgst,
        grand_total=grand_total,
        payment_method="Cash"  # Update with actual payment method if needed
    )


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

pre_approved_emails = ["project.spillbill@gmail.com","saivatsias@gmail.com","manitjha032@gmail.com","rohitgangwar49752@gmail.com"
,"vabhravi22@gmail.com","daksh.kasana19@gmail.com"]


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
