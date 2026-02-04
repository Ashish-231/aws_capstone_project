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

# IAM Role will auto authenticate
dynamodb = boto3.resource("dynamodb", region_name=REGION)
sns = boto3.client("sns", region_name=REGION)

# -------------------- DynamoDB Tables --------------------
users_table = dynamodb.Table("Users")
rooms_table = dynamodb.Table("Rooms")
bookings_table = dynamodb.Table("Bookings")


# -------------------- Home --------------------
@app.route("/")
def home():
    return render_template("index.html")


# -------------------- Register --------------------
@app.route("/register", methods=["GET", "POST"])
def register():

    if request.method == "POST":

        name = request.form["name"]
        email = request.form["email"]
        password = request.form["password"]
        role = request.form["role"]

        user_id = str(uuid.uuid4())

        user = {
            "user_id": user_id,
            "name": name,
            "email": email,
            "password": password,   # (Hash later in future)
            "role": role
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

        response = users_table.scan()
        users = response.get("Items", [])

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

    response = rooms_table.scan()
    rooms_data = response.get("Items", [])

    return render_template(
        "rooms.html",
        rooms=rooms_data,
        selected_type="",
        selected_price="",
        selected_guests=""
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

    if request.method == "POST":

        checkin = request.form["checkin"]
        checkout = request.form["checkout"]
        guests = request.form["guests"]

        booking_id = str(uuid.uuid4())

        booking = {
            "booking_id": booking_id,
            "user_id": session["user_id"],
            "user_name": session["name"],
            "room_id": room_id,
            "room_name": room["name"],
            "checkin": checkin,
            "checkout": checkout,
            "guests": guests,
            "price": room["price"],
            "created_at": datetime.now().isoformat()
        }

        # Save booking
        bookings_table.put_item(Item=booking)

        # Update room status
        rooms_table.update_item(
            Key={"room_id": room_id},
            UpdateExpression="SET #s = :s",
            ExpressionAttributeNames={"#s": "status"},
            ExpressionAttributeValues={":s": "Booked"}
        )

        # Send SNS Email
        message = f"""
Hello {session['name']},

Your booking is confirmed!

Room: {room['name']}
Check-in: {checkin}
Check-out: {checkout}
Booking ID: {booking_id}

Thank you,
Blissful Abodes
"""

        sns.publish(
            TopicArn=SNS_TOPIC_ARN,
            Message=message,
            Subject="Hotel Booking Confirmation"
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

    response = bookings_table.scan()
    bookings = response.get("Items", [])

    user_bookings = [
        b for b in bookings if b["user_id"] == session["user_id"]
    ]

    return render_template("my_bookings.html", bookings=user_bookings)


# -------------------- Staff Panel --------------------
@app.route("/staff", methods=["GET", "POST"])
def staff_panel():

    if "role" not in session or session["role"] != "staff":
        flash("Unauthorized access ❌", "error")
        return redirect(url_for("dashboard"))

    if request.method == "POST":

        room_id = request.form["room_id"]
        status = request.form["status"]

        rooms_table.update_item(
            Key={"room_id": room_id},
            UpdateExpression="SET #s = :s",
            ExpressionAttributeNames={"#s": "status"},
            ExpressionAttributeValues={":s": status}
        )

        flash("Room updated ✅", "success")
        return redirect(url_for("staff_panel"))

    rooms = rooms_table.scan().get("Items", [])

    return render_template("staff.html", rooms=rooms)


# -------------------- Admin Dashboard --------------------
@app.route("/admin")
def admin():

    if "role" not in session or session["role"] != "admin":
        flash("Unauthorized access ❌", "error")
        return redirect(url_for("dashboard"))

    rooms = rooms_table.scan().get("Items", [])
    bookings = bookings_table.scan().get("Items", [])
    users = users_table.scan().get("Items", [])

    total_rooms = len(rooms)
    booked = len([r for r in rooms if r["status"] == "Booked"])
    available = total_rooms - booked

    revenue = sum([int(b["price"]) for b in bookings])

    return render_template(
        "admin.html",
        total_rooms=total_rooms,
        booked_rooms=booked,
        available_rooms=available,
        total_bookings=len(bookings),
        revenue_estimate=revenue,
        total_users=len(users)
    )


# -------------------- Run Server --------------------
if __name__ == "__main__":

    app.run(
        host="0.0.0.0",
        port=5000,
        debug=True
    )
 