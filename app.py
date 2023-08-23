import os

from cs50 import SQL
from flask import Flask, flash, redirect, render_template, request, session
from flask_session import Session
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)

# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")


@app.after_request
def after_request(response):
    """Ensure responses aren't cached"""
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response


@app.route("/")
@login_required
def index():
    """Show portfolio of stocks"""
    user_id = session["user_id"]
    stocks = db.execute(
        "SELECT stock, price, SUM(shares) AS shares_total, SUM(price * shares) AS total_value FROM transactions WHERE user_id = ? GROUP BY stock;",
        user_id,
    )
    cash = db.execute("SELECT cash FROM users WHERE id = ?;", user_id)[0]["cash"]
    grand_total = cash

    for stock in stocks:
        grand_total += stock["total_value"]

    return render_template(
        "index.html", stocks=stocks, cash=cash, grand_total=grand_total, usd=usd
    )


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""
    if request.method == "POST":
        symbol = request.form.get("symbol")
        if not symbol:
            return apology("symbol cannot be empty")

        quote = lookup(symbol)
        if not quote:
            return apology("invalid symbol")

        shares = request.form.get("shares")
        try:
            shares = int(shares)
            if shares < 1:
                raise ValueError
        except ValueError:
            return apology("shares must be a positive integer")

        user_id = session["user_id"]
        cash = db.execute("SELECT cash FROM users WHERE id = ?", user_id)[0]["cash"]
        total_price = quote["price"] * shares

        if cash < total_price:
            return apology("not enough cash")

        db.execute(
            "UPDATE users SET cash = ? WHERE id = ?;", cash - total_price, user_id
        )

        db.execute(
            "INSERT INTO transactions (user_id, stock, symbol, price, shares, type) VALUES (?, ?, ?, ?, ?, ?);",
            user_id,
            quote["name"],
            quote["symbol"],
            quote["price"],
            shares,
            "buy",
        )

        return redirect("/")
    else:
        return render_template("buy.html")


@app.route("/history")
@login_required
def history():
    """Show history of transactions"""
    user_id = session["user_id"]
    transactions = db.execute(
        "SELECT symbol, price, shares, datetime, type FROM transactions WHERE user_id = ? ORDER BY datetime DESC;",
        user_id,
    )
    return render_template("history.html", transactions=transactions, usd=usd)


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":
        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Query database for username
        rows = db.execute(
            "SELECT * FROM users WHERE username = ?", request.form.get("username")
        )

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(
            rows[0]["hash"], request.form.get("password")
        ):
            return apology("invalid username and/or password", 403)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    """Get stock quote."""
    if request.method == "POST":
        symbol = request.form.get("symbol")

        if not symbol:
            return apology("enter a stock symbol")

        quote = lookup(symbol)

        if not quote:
            return apology("invalid symbol")

        return render_template(
            "quoted.html", stock=quote, stock_price=usd(quote["price"])
        )
    else:
        return render_template("quote.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""
    session.clear()

    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        confirmation = request.form.get("confirmation")

        if not username:
            return apology("username must not be empty")
        elif not password:
            return apology("password must not be empty")
        elif not confirmation:
            return apology("confirmation must match password")

        if password != confirmation:
            return apology("passwords do not match")

        hash = generate_password_hash(password)

        try:
            db.execute(
                "INSERT INTO users (username, hash) VALUES (?, ?);", username, hash
            )
        except:
            return apology("username has been taken")

        return redirect("/")
    else:
        return render_template("register.html")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""
    user_id = session["user_id"]

    if request.method == "POST":
        symbol = request.form.get("symbol")
        if not symbol:
            return apology("symbol cannot be empty")

        shares = request.form.get("shares")
        if not shares:
            return apology("shares must not be empty")

        quote = lookup(symbol)

        shares_owned = db.execute(
            "SELECT SUM(shares) AS owned FROM transactions WHERE symbol = ? AND user_id = ? GROUP BY stock;",
            quote["symbol"],
            user_id,
        )[0]["owned"]

        cash = db.execute("SELECT cash FROM users WHERE id = ?;", user_id)[0]["cash"]

        try:
            shares = int(shares)
            if shares < 1:
                raise ValueError
        except ValueError:
            return apology("shares must be a positive integer")

        if shares_owned < shares:
            return apology("insufficient quantity of shares")

        db.execute(
            "UPDATE users SET cash = ? WHERE id = ?;",
            cash + quote["price"] * shares,
            user_id,
        )

        db.execute(
            "INSERT INTO transactions (user_id, stock, symbol, price, shares, type) VALUES (?, ?, ?, ?, ?, ?);",
            user_id,
            quote["name"],
            quote["symbol"],
            quote["price"],
            -abs(shares),
            "sell",
        )

        return redirect("/")
    else:
        shareholds = db.execute(
            "SELECT symbol FROM transactions WHERE user_id = ? GROUP BY symbol;",
            user_id,
        )
        return render_template("sell.html", shareholds=shareholds)
