"""Training material for the Vanna NL->SQL model.

Vanna is a RAG framework: at query time it retrieves the most relevant of these
docs and example (question, SQL) pairs and feeds them to the LLM. Good training
data is what makes generated SQL reliable on join-heavy apparel questions.
"""

# Plain-English business rules and relationships the model can't infer from DDL alone.
VANNA_DOCUMENTATION: list[str] = [
    "finished_goods is the product catalogue. Each row is a style identified by "
    "style_number (primary key) with style_name, category (e.g. T-Shirt, Hoodie, "
    "Shirt, Polo, Jacket, Shorts, Trousers, Sweatshirt, Skirt, Dress), fabric, gsm, "
    "color, print, season, brand, supplier, cost and selling_price.",
    "Revenue and order value are computed as quantity * unit_price from sales_orders. "
    "There is no revenue column anywhere in the schema.",
    "Relationships: sales_orders.buyer references buyers.company_name; "
    "sales_orders.style_number references finished_goods.style_number; "
    "finished_goods.supplier references suppliers.company_name; "
    "sales_invoices.sales_order references sales_orders.order_number; "
    "tech_packs.style_number references finished_goods.style_number.",
    "To connect a buyer to the products they ordered, join buyers -> sales_orders "
    "(on buyer = company_name) -> finished_goods (on style_number).",
    "To connect a product to its supplier's details, join finished_goods.supplier = "
    "suppliers.company_name.",
    "GSM is the fabric weight in grams per square meter, stored as finished_goods.gsm "
    "(integer). 'above 220 GSM' means gsm > 220.",
    "Payment status values in sales_invoices.payment_status include 'Paid', 'Pending', "
    "'Partially Paid' and 'Overdue'. Pending / unpaid invoices are rows where "
    "payment_status <> 'Paid'.",
    "Match textual attributes case-insensitively with ILIKE. Denim products are "
    "finished_goods where fabric ILIKE '%denim%'; cotton products where fabric ILIKE "
    "'%cotton%'. Colors and prints should also be matched with ILIKE.",
    "suppliers.rating is a 0-5 quality score and suppliers.lead_time_days is the "
    "production lead time in days. tech_packs holds construction and fabric_details "
    "per style_number (one tech pack per style).",
    "Always return read-only SELECT queries. Prefer explicit JOINs and GROUP BY, and "
    "add ORDER BY with LIMIT when the question asks for 'top', 'highest' or 'most'.",
]

# Curated question -> SQL pairs covering the assessment's example questions plus
# common analytics. All are read-only SELECTs against the real schema.
VANNA_EXAMPLES: list[tuple[str, str]] = [
    (
        "Which buyer generated the highest revenue?",
        "SELECT buyer, SUM(quantity * unit_price) AS total_revenue "
        "FROM sales_orders GROUP BY buyer ORDER BY total_revenue DESC LIMIT 1",
    ),
    (
        "Which supplier supplied the most denim products?",
        "SELECT supplier, COUNT(*) AS denim_products FROM finished_goods "
        "WHERE fabric ILIKE '%denim%' GROUP BY supplier ORDER BY denim_products DESC LIMIT 1",
    ),
    (
        "Show all black hoodies under 900",
        "SELECT style_number, style_name, color, selling_price FROM finished_goods "
        "WHERE category ILIKE 'hoodie' AND color ILIKE '%black%' AND selling_price < 900 "
        "ORDER BY selling_price",
    ),
    (
        "Show pending invoices above 1000",
        "SELECT invoice_number, sales_order, amount, currency, payment_status "
        "FROM sales_invoices WHERE payment_status <> 'Paid' AND amount > 1000 "
        "ORDER BY amount DESC",
    ),
    (
        "Which buyers purchased garments above 220 GSM?",
        "SELECT DISTINCT so.buyer FROM sales_orders so "
        "JOIN finished_goods fg ON so.style_number = fg.style_number "
        "WHERE fg.gsm > 220 ORDER BY so.buyer",
    ),
    (
        "Show me all cotton shirts supplied by ABC Textiles",
        "SELECT style_number, style_name, fabric, supplier FROM finished_goods "
        "WHERE fabric ILIKE '%cotton%' AND category ILIKE 'shirt' AND supplier ILIKE '%ABC Textiles%'",
    ),
    (
        "Which supplier has the highest average order value?",
        "SELECT fg.supplier, AVG(so.quantity * so.unit_price) AS avg_order_value "
        "FROM sales_orders so JOIN finished_goods fg ON so.style_number = fg.style_number "
        "GROUP BY fg.supplier ORDER BY avg_order_value DESC LIMIT 1",
    ),
    (
        "Top 5 suppliers by number of orders",
        "SELECT fg.supplier, COUNT(*) AS order_count "
        "FROM sales_orders so JOIN finished_goods fg ON so.style_number = fg.style_number "
        "GROUP BY fg.supplier ORDER BY order_count DESC LIMIT 5",
    ),
    (
        "Show blue striped shirts",
        "SELECT style_number, style_name, color, print FROM finished_goods "
        "WHERE category ILIKE 'shirt' AND color ILIKE '%blue%' AND print ILIKE '%strip%'",
    ),
    (
        "Products with the highest selling price",
        "SELECT style_number, style_name, category, selling_price "
        "FROM finished_goods ORDER BY selling_price DESC LIMIT 10",
    ),
    (
        "How many orders are in each status?",
        "SELECT status, COUNT(*) AS orders FROM sales_orders GROUP BY status ORDER BY orders DESC",
    ),
    (
        "What is the total pending invoice amount?",
        "SELECT SUM(amount) AS pending_amount FROM sales_invoices WHERE payment_status <> 'Paid'",
    ),
    (
        "Which category has the most products?",
        "SELECT category, COUNT(*) AS products FROM finished_goods "
        "GROUP BY category ORDER BY products DESC LIMIT 1",
    ),
    (
        "List the top rated suppliers",
        "SELECT company_name, rating, country FROM suppliers ORDER BY rating DESC LIMIT 5",
    ),
    (
        "Average GSM by category",
        "SELECT category, ROUND(AVG(gsm)) AS avg_gsm FROM finished_goods "
        "GROUP BY category ORDER BY avg_gsm DESC",
    ),
]
