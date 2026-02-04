from flask import Flask, render_template, request, redirect, url_for, flash, session
from datetime import datetime

app = Flask(__name__)
app.secret_key = "blissful_abodes_secret_key"

# Temporary in-memory bookings list (Later replace with DynamoDB)
BOOKINGS = []
USERS = []

# ---------------- Role Protection ----------------
def require_role(role):
    if "role" not in session:
        return False
    return session["role"] == role



# Sample rooms (Later replace with DynamoDB)
ROOMS = [
    {
        "id": "R101",
        "name": "Deluxe Sea View",
        "type": "Deluxe",
        "price": 2499,
        "guests": 2,
        "status": "Available",
        "features": ["WiFi", "AC", "Sea View", "Breakfast"]
    },
    {
        "id": "R102",
        "name": "Premium Suite",
        "type": "Suite",
        "price": 4999,
        "guests": 4,
        "status": "Available",
        "features": ["WiFi", "AC", "Balcony", "Bathtub"]
    },
    {
        "id": "R103",
        "name": "Standard Room",
        "type": "Standard",
        "price": 1599,
        "guests": 2,
        "status": "Booked",
        "features": ["WiFi", "Fan", "TV"]
    },
    {
        "id": "R104",
        "name": "Family Comfort Room",
        "type": "Family",
        "price": 3299,
        "guests": 5,
        "status": "Available",
        "features": ["WiFi", "AC", "Extra Bed", "Mini Fridge"]
    }
]

@app.route("/")
def home():
    return render_template("index.html")

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":

        name = request.form.get("name")
        email = request.form.get("email")
        password = request.form.get("password")

        # Check duplicate email
        for u in USERS:
            if u["email"] == email:
                flash("Email already registered ❌", "error")
                return redirect(url_for("register"))
        
        role = request.form.get("role")


        user = {
            "name": name,
            "email": email,
            "password": password,
            "role": role
        }

        USERS.append(user)

        flash("Account created successfully ✅", "success")
        return redirect(url_for("login"))

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        email = request.form.get("email")
        password = request.form.get("password")

        for user in USERS:

            if user["email"] == email and user["password"] == password:

                # Save user in session
                session["user_id"] = user["email"]   # simple id for local app
                session["user_name"] = user["name"]
                session["user_email"] = user["email"]
                session["role"] = user["role"]



                flash("Login successful ✅", "success")
                return redirect(url_for("dashboard"))

        flash("Invalid email or password ❌", "error")

    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    flash("Logged out successfully ✅", "success")
    return redirect(url_for("home"))


@app.route("/dashboard")
def dashboard():

    if "user_id" not in session:
        return redirect(url_for("login"))

    role = session.get("role")

    if role == "admin":
        return redirect(url_for("admin"))

    if role == "staff":
        return redirect(url_for("staff_panel"))

    return render_template("dashboard.html")  # guest


@app.route("/rooms", methods=["GET"])
def rooms():
    room_type = request.args.get("type", "").strip()
    max_price = request.args.get("max_price", "").strip()
    guests = request.args.get("guests", "").strip()

    filtered_rooms = ROOMS

    if room_type:
        filtered_rooms = [r for r in filtered_rooms if r["type"].lower() == room_type.lower()]

    if max_price.isdigit():
        filtered_rooms = [r for r in filtered_rooms if r["price"] <= int(max_price)]

    if guests.isdigit():
        filtered_rooms = [r for r in filtered_rooms if r["guests"] >= int(guests)]

    return render_template(
        "rooms.html",
        rooms=filtered_rooms,
        selected_type=room_type,
        selected_price=max_price,
        selected_guests=guests
    )

# ✅ Booking Page
@app.route("/book/<room_id>", methods=["GET", "POST"])
def book_room(room_id):
    room = next((r for r in ROOMS if r["id"] == room_id), None)

    if not room:
        flash("Room not found ❌", "error")
        return redirect(url_for("rooms"))

    if room["status"] != "Available":
        flash("This room is not available right now ❌", "error")
        return redirect(url_for("rooms"))

    # ✅ When user clicks Confirm Booking
    if request.method == "POST":
        full_name = request.form.get("full_name")
        email = request.form.get("email")
        checkin = request.form.get("checkin")
        checkout = request.form.get("checkout")
        guests = request.form.get("guests")

        # ✅ If any field missing
        if not full_name or not email or not checkin or not checkout or not guests:
            flash("Please fill all details ❌", "error")
            return redirect(url_for("book_room", room_id=room_id))

        booking_id = f"BKG{len(BOOKINGS) + 1:03d}"

        booking = {
            "booking_id": booking_id,
            "room_id": room["id"],
            "room_name": room["name"],
            "full_name": full_name,
            "email": email,
            "checkin": checkin,
            "checkout": checkout,
            "guests": guests,
            "price_per_night": room["price"],
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }

        BOOKINGS.append(booking)

        # ✅ Mark room as booked (demo)
        room["status"] = "Booked"

        # ✅ MUST return redirect
        return redirect(url_for("booking_success", booking_id=booking_id))

    # ✅ For normal page open (GET request)
    return render_template("book.html", room=room)

@app.route("/booking-success/<booking_id>")
def booking_success(booking_id):
    booking = next((b for b in BOOKINGS if b["booking_id"] == booking_id), None)

    if not booking:
        flash("Booking not found ❌", "error")
        return redirect(url_for("rooms"))

    return render_template("booking_success.html", booking=booking)


@app.route("/my-bookings")
def my_bookings():

    if "user_id" not in session:
        return redirect(url_for("login"))

    return render_template("my_bookings.html", bookings=BOOKINGS)


@app.route("/staff", methods=["GET", "POST"])
def staff_panel():

    if not require_role("staff"):
        flash("Staff access only ❌", "error")
        return redirect(url_for("dashboard"))


    if request.method == "POST":
        room_id = request.form.get("room_id")
        new_status = request.form.get("status")

        room = next((r for r in ROOMS if r["id"] == room_id), None)
        if room:
            room["status"] = new_status
            flash(f"Room {room_id} status updated to {new_status} ✅", "success")
        else:
            flash("Room not found ❌", "error")

        return redirect(url_for("staff_panel"))

    return render_template("staff.html", rooms=ROOMS)

@app.route("/admin")
def admin_dashboard():

    if not require_role("admin"):
        flash("Admin access only ❌", "error")
        return redirect(url_for("dashboard"))

    total_rooms = len(ROOMS)
    available_rooms = len([r for r in ROOMS if r["status"] == "Available"])
    booked_rooms = len([r for r in ROOMS if r["status"] == "Booked"])
    total_bookings = len(BOOKINGS)

    revenue_estimate = sum([b["price_per_night"] for b in BOOKINGS])  # simple estimate

    return render_template(
        "admin.html",
        total_rooms=total_rooms,
        available_rooms=available_rooms,
        booked_rooms=booked_rooms,
        total_bookings=total_bookings,
        revenue_estimate=revenue_estimate
    )


if __name__ == "__main__":
    app.run(debug=True)
