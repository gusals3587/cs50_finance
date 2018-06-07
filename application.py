from cs50 import SQL
from flask import Flask, flash, redirect, render_template, request, session, url_for
from flask_session import Session
from passlib.apps import custom_app_context as pwd_context
from tempfile import mkdtemp
from datetime import datetime

from helpers import *

# configure application
app = Flask(__name__)

# ensure responses aren't cached
if app.config["DEBUG"]:
    @app.after_request
    def after_request(response):
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Expires"] = 0
        response.headers["Pragma"] = "no-cache"
        return response

# custom filter
app.jinja_env.filters["usd"] = usd

# configure session to use filesystem (instead of signed cookies)
app.config["SESSION_FILE_DIR"] = mkdtemp()
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")

# check for existence of certain attributes of request
def check_existence(attributes):
    for attribute in attributes:
        if not request.form.get(attribute):
            return apology("must provide {}".format(attribute))

# get how many of which stocks the user has, calculating and filtering out sold stocks
def get_user_stock(username): 

    # getting each holding's symbol and quantity (subtracting any stock with the sold flag raised)
    purchases = db.execute(("SELECT symbol, "
            "(SELECT IFNULL(SUM(quantity), 0) FROM purchases AS purchase WHERE purchase.symbol = purchases.symbol AND username = :username AND sold = 0) - "
            "(SELECT IFNULL(SUM(quantity), 0) FROM purchases AS purchase WHERE purchase.symbol = purchases.symbol AND username = :username AND sold != 0) AS quantity "
            "FROM purchases WHERE username = :username GROUP BY symbol;"), username=username)

    # filtering any stock with 0 or less quantity (compeletely sold stocks)
    purchases = [purchase for purchase in purchases if purchase["quantity"] > 0]

    return purchases

@app.route("/")
@login_required
def index():

    # getting the user info
    user = db.execute("SELECT * FROM users WHERE id = :user_id", user_id=session["user_id"])[0]

    # get user stock
    purchases = get_user_stock(user["username"])

    grand_total = 0

    for index, purchase in enumerate(purchases):

        # looking up the CURRENT price of each stock's price and calculating the value of each holding
        price = lookup(purchase["symbol"])["price"]
        total_price = price * purchase["quantity"]

        # add value of each stock and total value of each holding to the end of each puchases
        purchases[index]['price'] = price
        purchases[index]['total_price'] = total_price

        # calculating the grand total
        grand_total += total_price

    # getting user's current cash
    user_cash = user["cash"]

    # finally, rendering everything with each stock's current price, symbol each holding's value, and grand total
    return render_template("index.html", purchases=purchases, grand_total=grand_total, user_cash=user_cash)

@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock."""

    # if the user got here by POST
    if request.method == "POST":

        # check if symbol is not None
        check_existence(["symbol", "quantity"])

        # get stock information
        stock = lookup(request.form.get("symbol"))

        # check for stock existence
        if not stock:
            return apology("symbol invalid")

        if int(request.form.get("quantity")) < 0:
            return apology("invalid number of stock")

        # get user information
        user = db.execute("SELECT * FROM users WHERE id = :user_id", user_id=session["user_id"])

        # check if user has enough cash
        if user[0]["cash"] >= int(request.form.get("quantity")) * stock["price"]:

            # the transaction itself
            db.execute("UPDATE users SET cash = :cash WHERE id = :user_id", cash=user[0]["cash"] - int(request.form.get("quantity")) * stock["price"], user_id=session["user_id"])

            # the transaction record (recording the username, date, stock's symbol, price, and quantity)
            db.execute("INSERT INTO purchases (username, date, symbol, price, quantity) VALUES (:username, DATETIME('now'), :symbol, :price, :quantity)", username=user[0]["username"], symbol=stock["symbol"], price=stock["price"], quantity=int(request.form.get("quantity")))

        else:
            return apology("not enough cash")

    if request.method == "GET":

        return render_template("buy.html")

    # go back to home page
    return redirect(url_for("index"))

@app.route("/history")
@login_required
def history():

    # get user information
    user = db.execute("SELECT * FROM users WHERE id = :user_id", user_id=session["user_id"])
    user = user[0]

    # get every transaction that the user has made
    purchases = db.execute("SELECT * FROM purchases WHERE username = :username", username=user["username"])

    return render_template("history.html", purchases=purchases) 

@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in."""

    # forget any user_id
    session.clear()

    # if user reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # check for existence of username and password
        check_existence(["username", "password"])

        # query database for username
        rows = db.execute("SELECT * FROM users WHERE username = :username", username=request.form.get("username"))

        # ensure username exists and password is correct
        if len(rows) != 1:
            return apology("invalid username")

        if pwd_context.verify(request.form.get("password"), rows[0]["hash"]):
            return apology("invalid password")

        # remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # redirect user to home page
        return redirect(url_for("index"))

    # else if user reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")

@app.route("/logout")
def logout():
    """Log user out."""

    # forget any user_id
    session.clear()

    # redirect user to login form
    return redirect(url_for("login"))

@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    """Get stock quote."""

    # if the client got here by POST
    if request.method == "POST":
        # lookup is in helper.py
        stock = lookup(request.form.get("symbol"))

        # if symbol is invalid, lookup() return None
        if stock:
            return render_template("quoted.html", stock=stock)
        else:
            return apology("invalid symbol")

    # if the user got here by GET
    else:
        return render_template("quote.html")

@app.route("/register", methods=["GET", "POST"])
def register(): 
    """Register user."""

    # forget any user_id
    session.clear()

    # if user reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # ensure username and password are submitted
        check_existence(["username", "password"])

        # ensure password and verification password match
        if request.form.get("password") != request.form.get("verify_password"):
            return apology("password not matched")

        # check for username uniqueness
        rows = db.execute("SELECT * FROM users WHERE username = :username", username=request.form.get("username"))
        if len(rows) != 0:
            return apology("username already selected")

        # the insertion of user (provided the user cooperated)
        db.execute("INSERT INTO users (username, hash) VALUES(:username, :hashed_password)", username=request.form.get("username"), hashed_password=pwd_context.hash(request.form.get("password")))
 
        # query database for username
        rows = db.execute("SELECT * FROM users WHERE username = :username", username=request.form.get("username"))

        # remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # user congratulation
        flash("congratualtion, you have been registered")

        # redirect user to home page
        return redirect(url_for("index"))

    # if the user got here by GET
    if request.method == 'GET':
        return render_template("register.html")

@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():

    # get user information
    user = db.execute("SELECT * FROM users WHERE id = :user_id", user_id=session["user_id"])

    user = user[0]

    # if user reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # get user stocks info
        user_stocks = get_user_stock(user["username"])

        # making a dict with each key representing a symbol with the value being the quantity of the stocks with that symbol
        user_stocks_quantity = {x["symbol"]: x["quantity"] for x in user_stocks}

        # iterate over every fields in the POST form
        for symbol, quantity in request.form.items():

            # check if stock's quantity is positive and compare how many stock the user can sell
            quantity = int(quantity)
            if quantity < 0 or quantity > user_stocks_quantity[symbol]:
                return apology("invalid number of stocks")

            # check if stock exist
            stock = lookup(symbol)
            if stock == None:
                return apology("invalid symbol")
            
            # the transaction itself
            db.execute("UPDATE users SET cash = :cash WHERE id = :user_id", cash=user["cash"] + (quantity * stock["price"]), user_id=session["user_id"])

            # the transaction record (recording the username, date, stock's symbol, price, and quantity) with the sold flag enabled
            db.execute("INSERT INTO purchases (username, date, symbol, price, quantity, sold) VALUES (:username, DATETIME('now'), :symbol, :price, :quantity, 1)", username=user["username"], symbol=symbol, price=stock["price"], quantity=quantity)

        # redirect user to home page
        return redirect(url_for("index"))

    if request.method == "GET":
 
        # get user stock
        purchases = get_user_stock(user["username"])
        return render_template("sell.html", purchases=purchases)
        
