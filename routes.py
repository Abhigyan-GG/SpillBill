from flask import render_template, request, redirect, url_for, jsonify, send_file
from app import app, db
from models import Product
from datetime import datetime
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
import qrcode
import os
import json


# Home route
@app.route('/')
def home():
    return render_template('home.html')


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
            return str(e)  # Handle errors gracefully
    return render_template('add_items.html')


# Customer details route
@app.route('/customer_details', methods=['GET', 'POST'])
def customer_details():
    if request.method == 'POST':
        customer_name = request.form['name']
        phone_number = request.form['phone']
        return redirect(url_for('scan_products', name=customer_name, phone=phone_number))
    return render_template('customer_details.html')


# Route to scan products and add by name
@app.route('/scan_products', methods=['GET', 'POST'])
def scan_products():
    customer_name = request.args.get('name')
    phone_number = request.args.get('phone')

    if request.method == 'POST':
        product_name = request.form['product_name']
        if product_name:
            product = Product.query.filter_by(name=product_name).first()
            if product:
                scanned_products = json.loads(request.form['scanned_products'])
                existing_product = next((p for p in scanned_products if p['name'] == product.name), None)
                if existing_product:
                    existing_product['quantity'] += 1
                else:
                    scanned_products.append({'name': product.name, 'price': product.price, 'quantity': 1})
                return render_template('scan_products.html', name=customer_name, phone=phone_number,
                                       scanned_products=scanned_products)
            else:
                return render_template('scan_products.html', name=customer_name, phone=phone_number,
                                       error="Product not found in inventory")
    return render_template('scan_products.html', name=customer_name, phone=phone_number)


# API to fetch product list for adding by name
@app.route('/api/products')
def get_products():
    products = Product.query.all()
    return jsonify([{'name': product.name, 'price': product.price} for product in products])


#route to Generate bill
# Ensure the bills directory exists
if not os.path.exists('bills'):
    os.makedirs('bills')


@app.route('/generate_bill', methods=['POST'])
def generate_bill():
    now = datetime.now()

    # Generate the filename with current date and time
    timestamp = now.strftime("%d-%m-%Y_%H-%M-%S")
    pdf_filename = f'bills/bill_{timestamp}.pdf'
    customer_name = request.form["name"]
    phone_number = request.form["phone"]
    cashier = "Your Cashier Name"  # Set cashier name
    bill_no = timestamp.replace('-', '').replace('_', '')  # Simplified example for bill number
    payment_method = "Cash/Card/UPI"  # Example placeholder

    # Parse the scanned products
    scanned_products = json.loads(request.form["products"])

    # Calculate totals
    subtotal = sum(product['price'] * product['quantity'] for product in scanned_products)
    cgst = subtotal * 0.025  # 2.5% CGST
    sgst = subtotal * 0.025  # 2.5% SGST
    grand_total = subtotal + cgst + sgst

    # Generate PDF file and save it
    c = canvas.Canvas(pdf_filename, pagesize=A4)
    width, height = A4

    # Title and Header
    c.setFont("Helvetica-Bold", 16)
    c.drawString(100, height - 80, f"SpillBILL - Customer Bill")
    c.setFont("Helvetica", 12)
    c.drawString(100, height - 110, f"Customer Name: {customer_name}")
    c.drawString(100, height - 130, f"Phone: {phone_number}")
    c.drawString(100, height - 150, f"Date: {now.strftime('%d/%m/%Y')}")
    c.drawString(100, height - 170, f"Time: {now.strftime('%H:%M:%S')}")
    c.drawString(100, height - 190, f"Bill No.: {bill_no}")
    c.drawString(100, height - 210, f"Cashier: {cashier}")
    c.drawString(100, height - 230, "Items Purchased:")

    # Table Headers
    c.setFont("Helvetica-Bold", 12)
    c.drawString(100, height - 260, "Item")
    c.drawString(250, height - 260, "Quantity")
    c.drawString(400, height - 260, "Price (₹)")

    # Table Content
    c.setFont("Helvetica", 12)
    y = height - 280
    for product in scanned_products:
        c.drawString(100, y, product['name'])
        c.drawString(250, y, str(product['quantity']))
        c.drawString(400, y, f"{product['price'] * product['quantity']:.2f}")
        y -= 20

    # Totals
    c.setFont("Helvetica-Bold", 12)
    y -= 20
    c.drawString(100, y, f"Subtotal: ₹{subtotal:.2f}")
    y -= 20
    c.drawString(100, y, f"CGST (2.5%): ₹{cgst:.2f}")
    y -= 20
    c.drawString(100, y, f"SGST (2.5%): ₹{sgst:.2f}")
    y -= 20
    c.drawString(100, y, f"Grand Total: ₹{grand_total:.2f}")
    y -= 40
    c.setFont("Helvetica-Oblique", 10)
    c.drawString(100, y, f"Payment Method: {payment_method}")
    c.drawString(100, y - 20, "Thank you for shopping with us!")

    # Save the PDF file
    c.save()
    print(f"Bill saved as {pdf_filename}")

    # Render total_bill.html with bill details
    return render_template(
        'total_bill.html',
        products=scanned_products,
        total_price=grand_total,
        date=now.strftime("%d/%m/%Y"),
        time=now.strftime("%H:%M:%S"),
        bill_no=bill_no,
        cashier=cashier,
        subtotal=subtotal,
        cgst=cgst,
        sgst=sgst,
        grand_total=grand_total,
        payment_method=payment_method,
        pdf_path=pdf_filename  # Path to the saved PDF file
    )
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
            return redirect(url_for('inventory'))
        except Exception as e:
            return str(e)  # Handle errors gracefully
    return render_template('delete_product.html', product=product)
