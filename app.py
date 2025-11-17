
from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func
from datetime import datetime, date
import os

app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///web_wonders.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SECRET_KEY"] = "change_me_for_production"

db = SQLAlchemy(app)

# ----------------------
# Database Models
# ----------------------

class Client(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    brand_name = db.Column(db.String(120))
    start_date = db.Column(db.Date, default=date.today)
    monthly_retainer = db.Column(db.Float, default=0.0)
    status = db.Column(db.String(20), default="active")  # active / paused / closed
    notes = db.Column(db.Text)

    content_items = db.relationship("ContentItem", backref="client", lazy=True)
    efforts = db.relationship("EffortLog", backref="client", lazy=True)
    invoices = db.relationship("ClientInvoice", backref="client", lazy=True)


class Employee(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    role = db.Column(db.String(120))
    email = db.Column(db.String(120))
    status = db.Column(db.String(20), default="active")

    tasks = db.relationship("Task", backref="assignee", lazy=True)


class ContentItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    client_id = db.Column(db.Integer, db.ForeignKey("client.id"), nullable=False)
    date = db.Column(db.Date, nullable=False)
    platform = db.Column(db.String(50))
    content_type = db.Column(db.String(50))  # post, reel, story, blog, email
    title = db.Column(db.String(200))
    caption = db.Column(db.Text)
    status = db.Column(db.String(20), default="planned")  # planned, done, overdue, skipped
    posted_url = db.Column(db.String(255))
    remarks = db.Column(db.Text)


class EffortLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    client_id = db.Column(db.Integer, db.ForeignKey("client.id"), nullable=False)
    date = db.Column(db.Date, nullable=False)
    posts_count = db.Column(db.Integer, default=0)
    reels_count = db.Column(db.Integer, default=0)
    time_minutes = db.Column(db.Integer, default=0)
    notes = db.Column(db.Text)


class Task(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    client_id = db.Column(db.Integer, db.ForeignKey("client.id"), nullable=True)
    assigned_to = db.Column(db.Integer, db.ForeignKey("employee.id"), nullable=True)
    status = db.Column(db.String(20), default="pending")  # pending, in_progress, completed, overdue
    priority = db.Column(db.String(20), default="medium")  # low, medium, high
    due_date = db.Column(db.Date, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class ClientInvoice(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    client_id = db.Column(db.Integer, db.ForeignKey("client.id"), nullable=False)
    month = db.Column(db.String(7), nullable=False)  # YYYY-MM
    amount = db.Column(db.Float, nullable=False)
    due_date = db.Column(db.Date, nullable=False)
    status = db.Column(db.String(20), default="pending")  # pending, paid, overdue
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    payments = db.relationship("ClientPayment", backref="invoice", lazy=True)


class ClientPayment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    client_id = db.Column(db.Integer, db.ForeignKey("client.id"), nullable=False)
    invoice_id = db.Column(db.Integer, db.ForeignKey("client_invoice.id"), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    payment_date = db.Column(db.Date, nullable=False)
    mode = db.Column(db.String(50))  # cash, bank_transfer, upi, card
    reference = db.Column(db.String(120))
    notes = db.Column(db.Text)


class PaymentOut(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    vendor_name = db.Column(db.String(120), nullable=False)
    related_client_id = db.Column(db.Integer, db.ForeignKey("client.id"), nullable=True)
    amount = db.Column(db.Float, nullable=False)
    payment_date = db.Column(db.Date, nullable=False)
    mode = db.Column(db.String(50))
    category = db.Column(db.String(50))  # software, salary, ads, others
    notes = db.Column(db.Text)


class Projection(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    period_type = db.Column(db.String(20), default="monthly")  # monthly, quarterly, yearly
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=False)
    target_revenue = db.Column(db.Float, nullable=False)
    target_clients_count = db.Column(db.Integer, nullable=False)
    description = db.Column(db.Text)


# ----------------------
# Helper functions
# ----------------------

def update_overdue_statuses():
    """Mark content items and invoices as overdue based on date."""
    today = date.today()

    # Content items
    items = ContentItem.query.filter(ContentItem.status != "done").all()
    for item in items:
        if item.date < today and item.status != "skipped":
            item.status = "overdue"

    # Invoices
    invoices = ClientInvoice.query.filter(ClientInvoice.status != "paid").all()
    for inv in invoices:
        if inv.due_date < today:
            inv.status = "overdue"

    db.session.commit()


def get_active_projection():
    today = date.today()
    return Projection.query.filter(
        Projection.start_date <= today,
        Projection.end_date >= today
    ).first()


# ----------------------
# Routes
# ----------------------

@app.route("/")
def dashboard():
    update_overdue_statuses()
    today = date.today()

    # Today's content
    todays_items = ContentItem.query.filter_by(date=today).order_by(ContentItem.client_id).all()

    # This week's content (simple: +/- 3 days)
    from datetime import timedelta
    start_week = today - timedelta(days=3)
    end_week = today + timedelta(days=3)
    weeks_items = ContentItem.query.filter(
        ContentItem.date >= start_week,
        ContentItem.date <= end_week
    ).order_by(ContentItem.date).all()

    # Overdue content
    overdue_items = ContentItem.query.filter_by(status="overdue").order_by(ContentItem.date).all()

    # Overdue invoices
    overdue_invoices = ClientInvoice.query.filter_by(status="overdue").order_by(ClientInvoice.due_date).all()

    # Effort summary: last 30 days
    from_date = today - timedelta(days=30)
    effort_rows = db.session.query(
        Client.name,
        func.sum(EffortLog.time_minutes).label("total_minutes")
    ).join(Client).filter(
        EffortLog.date >= from_date,
        EffortLog.date <= today
    ).group_by(Client.id).all()

    total_minutes = sum(row.total_minutes for row in effort_rows) or 0
    effort_summary = []
    for row in effort_rows:
        pct = (row.total_minutes / total_minutes * 100) if total_minutes else 0
        effort_summary.append({
            "client_name": row[0],
            "total_minutes": row[1],
            "percentage": round(pct, 1)
        })
    effort_summary_sorted = sorted(effort_summary, key=lambda x: x["total_minutes"], reverse=True)
    top_client = effort_summary_sorted[0] if effort_summary_sorted else None

    # Projection
    projection = get_active_projection()
    projection_progress = None
    if projection:
        # Calculate achieved revenue & clients in period
        achieved_revenue = db.session.query(func.sum(ClientInvoice.amount)).filter(
            ClientInvoice.status == "paid",
            ClientInvoice.due_date >= projection.start_date,
            ClientInvoice.due_date <= projection.end_date
        ).scalar() or 0

        client_ids = db.session.query(ClientInvoice.client_id).filter(
            ClientInvoice.status == "paid",
            ClientInvoice.due_date >= projection.start_date,
            ClientInvoice.due_date <= projection.end_date
        ).distinct().all()
        achieved_clients = len(client_ids)

        revenue_pct = (achieved_revenue / projection.target_revenue * 100) if projection.target_revenue else 0
        client_pct = (achieved_clients / projection.target_clients_count * 100) if projection.target_clients_count else 0

        projection_progress = {
            "achieved_revenue": achieved_revenue,
            "achieved_clients": achieved_clients,
            "revenue_pct": round(revenue_pct, 1),
            "client_pct": round(client_pct, 1)
        }

    return render_template(
        "dashboard.html",
        todays_items=todays_items,
        weeks_items=weeks_items,
        overdue_items=overdue_items,
        overdue_invoices=overdue_invoices,
        top_client=top_client,
        effort_summary=effort_summary_sorted,
        projection=projection,
        projection_progress=projection_progress,
    )


# -------- Clients --------

@app.route("/clients")
def clients():
    q = request.args.get("q", "")
    query = Client.query
    if q:
        query = query.filter(Client.name.ilike(f"%{q}%"))
    all_clients = query.order_by(Client.name).all()
    return render_template("clients.html", clients=all_clients, q=q)


@app.route("/clients/new", methods=["GET", "POST"])
def new_client():
    if request.method == "POST":
        name = request.form.get("name")
        brand_name = request.form.get("brand_name")
        start_date_str = request.form.get("start_date")
        monthly_retainer = float(request.form.get("monthly_retainer") or 0)
        status = request.form.get("status") or "active"
        notes = request.form.get("notes")

        start_date_val = date.fromisoformat(start_date_str) if start_date_str else date.today()

        client = Client(
            name=name,
            brand_name=brand_name,
            start_date=start_date_val,
            monthly_retainer=monthly_retainer,
            status=status,
            notes=notes,
        )
        db.session.add(client)
        db.session.commit()
        flash("Client created successfully!", "success")
        return redirect(url_for("clients"))

    return render_template("client_form.html", client=None)


@app.route("/clients/<int:client_id>/edit", methods=["GET", "POST"])
def edit_client(client_id):
    client = Client.query.get_or_404(client_id)
    if request.method == "POST":
        client.name = request.form.get("name")
        client.brand_name = request.form.get("brand_name")
        start_date_str = request.form.get("start_date")
        client.start_date = date.fromisoformat(start_date_str) if start_date_str else client.start_date
        client.monthly_retainer = float(request.form.get("monthly_retainer") or 0)
        client.status = request.form.get("status") or client.status
        client.notes = request.form.get("notes")
        db.session.commit()
        flash("Client updated!", "success")
        return redirect(url_for("clients"))

    return render_template("client_form.html", client=client)


# -------- Content Planner --------

@app.route("/planner")
def planner():
    client_id = request.args.get("client_id", type=int)
    month_str = request.args.get("month")  # format YYYY-MM
    today = date.today()
    if not month_str:
        month_str = today.strftime("%Y-%m")

    year, month = map(int, month_str.split("-"))
    from datetime import timedelta
    start_date = date(year, month, 1)
    # compute end of month
    if month == 12:
        end_date = date(year + 1, 1, 1) - timedelta(days=1)
    else:
        end_date = date(year, month + 1, 1) - timedelta(days=1)

    query = ContentItem.query.filter(
        ContentItem.date >= start_date,
        ContentItem.date <= end_date
    )
    if client_id:
        query = query.filter(ContentItem.client_id == client_id)
    items = query.order_by(ContentItem.date).all()

    clients = Client.query.order_by(Client.name).all()

    return render_template(
        "planner.html",
        items=items,
        clients=clients,
        selected_client_id=client_id,
        month_str=month_str,
        start_date=start_date,
        end_date=end_date,
    )


@app.route("/planner/new", methods=["GET", "POST"])
def planner_new():
    clients = Client.query.order_by(Client.name).all()
    if request.method == "POST":
        client_id = int(request.form.get("client_id"))
        date_str = request.form.get("date")
        platform = request.form.get("platform")
        content_type = request.form.get("content_type")
        title = request.form.get("title")
        caption = request.form.get("caption")

        item = ContentItem(
            client_id=client_id,
            date=date.fromisoformat(date_str),
            platform=platform,
            content_type=content_type,
            title=title,
            caption=caption,
            status="planned",
        )
        db.session.add(item)
        db.session.commit()
        flash("Content item added!", "success")
        return redirect(url_for("planner"))

    return render_template("planner_form.html", clients=clients, item=None)


@app.route("/planner/<int:item_id>/edit", methods=["GET", "POST"])
def planner_edit(item_id):
    item = ContentItem.query.get_or_404(item_id)
    clients = Client.query.order_by(Client.name).all()
    if request.method == "POST":
        item.client_id = int(request.form.get("client_id"))
        date_str = request.form.get("date")
        item.date = date.fromisoformat(date_str)
        item.platform = request.form.get("platform")
        item.content_type = request.form.get("content_type")
        item.title = request.form.get("title")
        item.caption = request.form.get("caption")
        item.status = request.form.get("status") or item.status
        item.posted_url = request.form.get("posted_url")
        item.remarks = request.form.get("remarks")
        db.session.commit()
        flash("Content item updated!", "success")
        return redirect(url_for("planner"))

    return render_template("planner_form.html", clients=clients, item=item)


@app.route("/planner/<int:item_id>/status/<status>")
def planner_status(item_id, status):
    item = ContentItem.query.get_or_404(item_id)
    if status in ["planned", "done", "overdue", "skipped"]:
        item.status = status
        db.session.commit()
        flash("Status updated!", "success")
    return redirect(request.referrer or url_for("planner"))


# -------- Effort Logs --------

@app.route("/efforts", methods=["GET", "POST"])
def efforts():
    clients = Client.query.order_by(Client.name).all()
    if request.method == "POST":
        client_id = int(request.form.get("client_id"))
        date_str = request.form.get("date")
        posts_count = int(request.form.get("posts_count") or 0)
        reels_count = int(request.form.get("reels_count") or 0)
        time_minutes = int(request.form.get("time_minutes") or 0)
        notes = request.form.get("notes")

        log = EffortLog(
            client_id=client_id,
            date=date.fromisoformat(date_str),
            posts_count=posts_count,
            reels_count=reels_count,
            time_minutes=time_minutes,
            notes=notes,
        )
        db.session.add(log)
        db.session.commit()
        flash("Effort log added!", "success")
        return redirect(url_for("efforts"))

    # filters
    client_id = request.args.get("client_id", type=int)
    period = request.args.get("period", "month")  # week / month

    today = date.today()
    from datetime import timedelta
    if period == "week":
        from_date = today - timedelta(days=7)
    else:
        from_date = today.replace(day=1)

    query = EffortLog.query.filter(
        EffortLog.date >= from_date,
        EffortLog.date <= today
    )
    if client_id:
        query = query.filter(EffortLog.client_id == client_id)
    logs = query.order_by(EffortLog.date.desc()).all()

    # summary
    effort_rows = db.session.query(
        Client.name,
        func.sum(EffortLog.time_minutes).label("total_minutes")
    ).join(Client).filter(
        EffortLog.date >= from_date,
        EffortLog.date <= today
    ).group_by(Client.id).all()

    total_minutes = sum(r.total_minutes for r in effort_rows) or 0
    summary = []
    for r in effort_rows:
        pct = (r.total_minutes / total_minutes * 100) if total_minutes else 0
        summary.append({
            "client_name": r[0],
            "total_minutes": r[1],
            "percentage": round(pct, 1)
        })
    summary = sorted(summary, key=lambda x: x["total_minutes"], reverse=True)

    return render_template(
        "efforts.html",
        logs=logs,
        summary=summary,
        clients=clients,
        selected_client_id=client_id,
        period=period,
    )


# -------- Tasks --------

@app.route("/tasks", methods=["GET", "POST"])
def tasks():
    clients = Client.query.order_by(Client.name).all()
    employees = Employee.query.order_by(Employee.name).all()

    if request.method == "POST":
        title = request.form.get("title")
        description = request.form.get("description")
        client_id = request.form.get("client_id")
        assigned_to = request.form.get("assigned_to")
        status = request.form.get("status") or "pending"
        priority = request.form.get("priority") or "medium"
        due_date_str = request.form.get("due_date")

        t = Task(
            title=title,
            description=description,
            client_id=int(client_id) if client_id else None,
            assigned_to=int(assigned_to) if assigned_to else None,
            status=status,
            priority=priority,
            due_date=date.fromisoformat(due_date_str) if due_date_str else None,
        )
        db.session.add(t)
        db.session.commit()
        flash("Task created!", "success")
        return redirect(url_for("tasks"))

    # filters
    status_filter = request.args.get("status")
    employee_id = request.args.get("employee_id", type=int)

    query = Task.query
    if status_filter:
        query = query.filter(Task.status == status_filter)
    if employee_id:
        query = query.filter(Task.assigned_to == employee_id)
    all_tasks = query.order_by(Task.due_date.is_(None), Task.due_date).all()

    return render_template(
        "tasks.html",
        tasks=all_tasks,
        clients=clients,
        employees=employees,
        status_filter=status_filter,
        employee_id=employee_id,
    )


@app.route("/tasks/<int:task_id>/status/<status>")
def task_status(task_id, status):
    t = Task.query.get_or_404(task_id)
    if status in ["pending", "in_progress", "completed", "overdue"]:
        t.status = status
        db.session.commit()
        flash("Task status updated!", "success")
    return redirect(request.referrer or url_for("tasks"))


# -------- Accounts --------

@app.route("/accounts", methods=["GET", "POST"])
def accounts():
    clients = Client.query.order_by(Client.name).all()

    if request.method == "POST":
        # Create invoice
        client_id = int(request.form.get("client_id"))
        month = request.form.get("month")  # YYYY-MM
        amount = float(request.form.get("amount") or 0)
        due_date_str = request.form.get("due_date")
        due_date_val = date.fromisoformat(due_date_str)

        inv = ClientInvoice(
            client_id=client_id,
            month=month,
            amount=amount,
            due_date=due_date_val,
            status="pending",
        )
        db.session.add(inv)
        db.session.commit()
        flash("Invoice created!", "success")
        return redirect(url_for("accounts"))

    # filters
    client_id = request.args.get("client_id", type=int)
    status_filter = request.args.get("status")

    query = ClientInvoice.query
    if client_id:
        query = query.filter(ClientInvoice.client_id == client_id)
    if status_filter:
        query = query.filter(ClientInvoice.status == status_filter)
    invoices = query.order_by(ClientInvoice.due_date.desc()).all()

    return render_template(
        "accounts.html",
        invoices=invoices,
        clients=clients,
        selected_client_id=client_id,
        status_filter=status_filter,
    )


@app.route("/accounts/<int:invoice_id>/pay", methods=["GET", "POST"])
def accounts_pay(invoice_id):
    inv = ClientInvoice.query.get_or_404(invoice_id)
    if request.method == "POST":
        amount = float(request.form.get("amount") or 0)
        payment_date_str = request.form.get("payment_date")
        mode = request.form.get("mode")
        reference = request.form.get("reference")
        notes = request.form.get("notes")

        pay = ClientPayment(
            client_id=inv.client_id,
            invoice_id=inv.id,
            amount=amount,
            payment_date=date.fromisoformat(payment_date_str),
            mode=mode,
            reference=reference,
            notes=notes,
        )
        db.session.add(pay)

        # if paid full, mark invoice as paid
        total_paid = db.session.query(func.sum(ClientPayment.amount)).filter(
            ClientPayment.invoice_id == inv.id
        ).scalar() or 0
        total_paid += amount
        if total_paid >= inv.amount:
            inv.status = "paid"

        db.session.commit()
        flash("Payment recorded!", "success")
        return redirect(url_for("accounts"))

    return render_template("payment_form.html", invoice=inv)


# -------- Projection Wall --------

@app.route("/projection", methods=["GET", "POST"])
def projection():
    if request.method == "POST":
        period_type = request.form.get("period_type")
        start_date_str = request.form.get("start_date")
        end_date_str = request.form.get("end_date")
        target_revenue = float(request.form.get("target_revenue") or 0)
        target_clients_count = int(request.form.get("target_clients_count") or 0)
        description = request.form.get("description")

        proj = Projection(
            period_type=period_type,
            start_date=date.fromisoformat(start_date_str),
            end_date=date.fromisoformat(end_date_str),
            target_revenue=target_revenue,
            target_clients_count=target_clients_count,
            description=description,
        )
        db.session.add(proj)
        db.session.commit()
        flash("Projection created!", "success")
        return redirect(url_for("projection"))

    projection = get_active_projection()
    today = date.today()
    projection_progress = None
    if projection:
        achieved_revenue = db.session.query(func.sum(ClientInvoice.amount)).filter(
            ClientInvoice.status == "paid",
            ClientInvoice.due_date >= projection.start_date,
            ClientInvoice.due_date <= projection.end_date
        ).scalar() or 0

        client_ids = db.session.query(ClientInvoice.client_id).filter(
            ClientInvoice.status == "paid",
            ClientInvoice.due_date >= projection.start_date,
            ClientInvoice.due_date <= projection.end_date
        ).distinct().all()
        achieved_clients = len(client_ids)

        revenue_pct = (achieved_revenue / projection.target_revenue * 100) if projection.target_revenue else 0
        client_pct = (achieved_clients / projection.target_clients_count * 100) if projection.target_clients_count else 0

        projection_progress = {
            "achieved_revenue": achieved_revenue,
            "achieved_clients": achieved_clients,
            "revenue_pct": round(revenue_pct, 1),
            "client_pct": round(client_pct, 1)
        }

    all_projections = Projection.query.order_by(Projection.start_date.desc()).all()

    return render_template(
        "projection.html",
        projection=projection,
        projection_progress=projection_progress,
        all_projections=all_projections,
        today=today,
    )


# -------- Global Search --------

@app.route("/search")
def search():
    q = request.args.get("q", "").strip()
    clients = []
    content_items = []
    tasks = []
    invoices = []

    if q:
        like = f"%{q}%"
        clients = Client.query.filter(Client.name.ilike(like)).all()
        content_items = ContentItem.query.filter(ContentItem.title.ilike(like)).all()
        tasks = Task.query.filter(Task.title.ilike(like)).all()
        invoices = ClientInvoice.query.join(Client).filter(Client.name.ilike(like)).all()

    return render_template(
        "search.html",
        q=q,
        clients=clients,
        content_items=content_items,
        tasks=tasks,
        invoices=invoices,
    )


# ----------------------
# CLI helper
# ----------------------

@app.cli.command("init-db")
def init_db():
    """Initialize the database."""
    with app.app_context():
        db.create_all()
if __name__ == "__main__":
    init_db()
    app.run(debug=True)
