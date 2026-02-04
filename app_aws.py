from flask import Flask, render_template, request, redirect, url_for, flash, session
import boto3
import uuid
from datetime import datetime

# -------------------- Flask App --------------------
app = Flask(__name__)
app.secret_key = "blissful_abodes_aws_secret"

# -------------------- AWS Config --------------------
REGION = "us-east-1"   # Change if needed
SNS_TOPIC_ARN = "PASTE_YOUR_SNS_TOPIC_ARN_HERE"

dynamodb = boto3.resource("dynamodb", region_name=REGION)
sns = boto3.client("sns", region_name=REGION)

# -------------------- Tables --------------------
users_table = dynamodb.Table("Users")
rooms_table = dynamodb.Table("Rooms")
bookings_table = dynamodb.Table("Bookings")


# -------------------- Helper: Scan All --------------------
def scan_all(table):
    data = []
    response = table.scan()
    data.extend(response.get("Items", []))

    while "LastEvaluatedKey" in response:
        response = table.scan(ExclusiveStartKey=response["LastEvaluatedKey"])
        data.extend(response.get("Items", []))

    return data


# -------------------- Home --------------------
@app.route("/")
def home():
    return render_template("index.html")


# -------------------- Register --------------------
@app.route("/register", methods=["GET", "POST"])
def register():

    if request.method == "POST":

        user = {
            "user_id": str(uuid.uuid4()),
            "name": request.form["name"],
            "email": request.form["email"],
            "password": request.form["password"],
            "role": request.form["role"]
        }

        users_table.put_item(Item=user)

        flash("Account created successfully ✅", "success")
        return redirect(url_for("login"))

    return render_template("register.html")


# -------------------- Login --------------------
@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        email = request.form["email"]
        password = request.form["password"]

        users = scan_all(users_table)

        for user in users:

            if user["email"] == email and user["password"] == password:

                session["user_id"] = user["user_id"]
                session["name"] = user["name"]
                session["role"] = user["role"]

                flash("Login successful ✅", "success")
                return redirect(url_for("dashboard"))

        flash("Invalid login ❌", "error")

    return render_template("login.html")


# -------------------- Logout --------------------
@app.route("/logout")
def logout():

    session.clear()
    flash("Logged out successfully ✅", "success")

    return redirect(url_for("home"))


# -------------------- Dashboard --------------------
@app.route("/dashboard")
def dashboard():

    if "user_id" not in session:
        return redirect(url_for("login"))

    return render_template("dashboard.html")


# -------------------- Rooms --------------------
@app.route("/rooms")
def rooms():

    room_type = request.args.get("type", "").strip()
    max_price = request.args.get("max_price", "").strip()
    guests = request.args.get("guests", "").strip()

    rooms_data = scan_all(rooms_table)

    # Map room_id -> id (Template compatibility)
    for r in rooms_data:
        r["id"] = r["room_id"]

    filtered = rooms_data

    if room_type:
        filtered = [r for r in filtered if r["type"].lower() == room_type.lower()]

    if max_price.isdigit():
        filtered = [r for r in filtered if int(r["price"]) <= int(max_price)]

    if guests.isdigit():
        filtered = [r for r in filtered if int(r["guests"]) >= int(guests)]

    return render_template(
        "rooms.html",
        rooms=filtered,
        selected_type=room_type,
        selected_price=max_price,
        selected_guests=guests
    )


# -------------------- Book Room --------------------
@app.route("/book/<room_id>", methods=["GET", "POST"])
def book_room(room_id):

    if "user_id" not in session:
        return redirect(url_for("login"))

    res = rooms_table.get_item(Key={"room_id": room_id})
    room = res.get("Item")

    if not room:
        flash("Room not found ❌", "error")
        return redirect(url_for("rooms"))

    if room["status"] != "Available":
        flash("Room already booked ❌", "error")
        return redirect(url_for("rooms"))

    # Map for template
    room["id"] = room["room_id"]

    if request.method == "POST":

        booking_id = str(uuid.uuid4())

        booking = {
            "booking_id": booking_id,
            "user_id": session["user_id"],
            "user_name": session["name"],
            "room_id": room_id,
            "room_name": room["name"],
            "checkin": request.form["checkin"],
            "checkout": request.form["checkout"],
            "guests": request.form["guests"],
            "price": room["price"],
            "created_at": datetime.now().isoformat()
        }

        bookings_table.put_item(Item=booking)

        # Update room
        rooms_table.update_item(
            Key={"room_id": room_id},
            UpdateExpression="SET #s = :s",
            ExpressionAttributeNames={"#s": "status"},
            ExpressionAttributeValues={":s": "Booked"}
        )

        # SNS Mail
        msg = f"""
Hello {session['name']},

Your booking is confirmed.

Room: {room['name']}
Booking ID: {booking_id}

Thank you,
Blissful Abodes
"""

        sns.publish(
            TopicArn=SNS_TOPIC_ARN,
            Message=msg,
            Subject="Booking Confirmation"
        )

        return redirect(url_for("booking_success", booking_id=booking_id))

    return render_template("book.html", room=room)


# -------------------- Booking Success --------------------
@app.route("/booking-success/<booking_id>")
def booking_success(booking_id):

    res = bookings_table.get_item(Key={"booking_id": booking_id})
    booking = res.get("Item")

    if not booking:
        flash("Booking not found ❌", "error")
        return redirect(url_for("rooms"))

    return render_template("booking_success.html", booking=booking)


# -------------------- My Bookings --------------------
@app.route("/my-bookings")
def my_bookings():

    if "user_id" not in session:
        return redirect(url_for("login"))

    bookings = scan_all(bookings_table)

    user_data = [
        b for b in bookings if b["user_id"] == session["user_id"]
    ]

    return render_template("my_bookings.html", bookings=user_data)


# -------------------- Staff Panel --------------------
@app.route("/staff", methods=["GET", "POST"])
def staff_panel():

    if session.get("role") != "staff":
        flash("Unauthorized ❌", "error")
        return redirect(url_for("dashboard"))

    if request.method == "POST":

        rooms_table.update_item(
            Key={"room_id": request.form["room_id"]},
            UpdateExpression="SET #s = :s",
            ExpressionAttributeNames={"#s": "status"},
            ExpressionAttributeValues={":s": request.form["status"]}
        )

        flash("Room updated ✅", "success")
        return redirect(url_for("staff_panel"))

    rooms = scan_all(rooms_table)

    for r in rooms:
        r["id"] = r["room_id"]

    return render_template("staff.html", rooms=rooms)


# -------------------- Admin --------------------
@app.route("/admin")
def admin():

    if session.get("role") != "admin":
        flash("Unauthorized ❌", "error")
        return redirect(url_for("dashboard"))

    rooms = scan_all(rooms_table)
    bookings = scan_all(bookings_table)
    users = scan_all(users_table)

    booked = len([r for r in rooms if r["status"] == "Booked"])

    revenue = 0
    for b in bookings:
        try:
            revenue += int(b["price"])
        except:
            pass

    return render_template(
        "admin.html",
        total_rooms=len(rooms),
        booked_rooms=booked,
        available_rooms=len(rooms) - booked,
        total_bookings=len(bookings),
        revenue_estimate=revenue,
        total_users=len(users)
    )


# -------------------- Run --------------------
if __name__ == "__main__":

    app.run(host="0.0.0.0", port=5000, debug=True)
