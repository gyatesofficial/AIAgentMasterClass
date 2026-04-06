#!/usr/bin/env python3
"""
seed_data.py - Generate realistic sample data for the support platform
======================================================================
Creates:
  - 100 support tickets  → data/sample_tickets.json
  - 50 KB articles       → data/knowledge_base.json

Usage:
    python scripts/seed_data.py

This data is used by:
  - module_06_rag  (embedding KB articles into ChromaDB)
  - module_10_evaluation  (benchmark test cases)
  - module_09_production  (API development / manual testing)
"""

import json
import random
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

# ──────────────────────────────────────────────────────────────
# Configuration
# ──────────────────────────────────────────────────────────────
RANDOM_SEED = 42
NUM_TICKETS = 100
NUM_KB_ARTICLES = 50

DATA_DIR = Path(__file__).parent.parent / "data"
TICKETS_FILE = DATA_DIR / "sample_tickets.json"
KB_FILE = DATA_DIR / "knowledge_base.json"

random.seed(RANDOM_SEED)

# ──────────────────────────────────────────────────────────────
# Sample data pools
# ──────────────────────────────────────────────────────────────

FIRST_NAMES = [
    "Alice", "Bob", "Carol", "David", "Eve", "Frank", "Grace", "Hank",
    "Ivy", "Jack", "Karen", "Leo", "Mia", "Nathan", "Olivia", "Paul",
    "Quinn", "Rachel", "Sam", "Tina", "Uma", "Victor", "Wendy", "Xander",
    "Yara", "Zoe", "Aaron", "Beth", "Carlos", "Diana",
]

LAST_NAMES = [
    "Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller",
    "Davis", "Martinez", "Wilson", "Anderson", "Taylor", "Thomas", "Hernandez",
    "Moore", "Martin", "Jackson", "Thompson", "White", "Lopez", "Lee",
    "Harris", "Clark", "Lewis", "Robinson", "Walker", "Young", "Hall",
    "Allen", "King",
]

EMAIL_DOMAINS = [
    "gmail.com", "outlook.com", "yahoo.com", "company.io", "startup.co",
    "enterprise.com", "consulting.net", "agency.org", "tech.dev",
]

SUBSCRIPTION_TIERS = ["free", "starter", "pro", "enterprise"]

CATEGORIES = [
    "account_access",
    "billing",
    "technical_bug",
    "feature_request",
    "general_inquiry",
]

PRIORITIES = ["low", "medium", "high", "critical"]
STATUSES = ["open", "in_progress", "resolved"]

# Probability weights for each status
STATUS_WEIGHTS = [0.4, 0.25, 0.35]

# Priority distribution (most tickets are medium)
PRIORITY_WEIGHTS = [0.2, 0.45, 0.25, 0.10]

# ──────────────────────────────────────────────────────────────
# Ticket templates per category
# ──────────────────────────────────────────────────────────────

TICKET_TEMPLATES = {
    "account_access": [
        {
            "subject": "Cannot log into my account",
            "body": "I've been trying to log in for the past hour but keep getting 'Invalid credentials' even though I'm sure my password is correct. I haven't changed it recently. My email is {email}. Please help!",
            "priority_bias": "high",
        },
        {
            "subject": "Account locked after too many attempts",
            "body": "My account got locked after I forgot my password and tried a few times. I've been a {tier} subscriber for {months} months and really need access. Can you unlock it?",
            "priority_bias": "high",
        },
        {
            "subject": "Two-factor authentication not working",
            "body": "The authenticator app codes for my account stopped working after I got a new phone. I can't log in and I have an important deadline today. My account email is {email}.",
            "priority_bias": "critical",
        },
        {
            "subject": "Password reset email not arriving",
            "body": "I requested a password reset 3 times but never received the email. I've checked spam and it's not there. My email is {email}.",
            "priority_bias": "medium",
        },
        {
            "subject": "Can't access my team workspace",
            "body": "My colleague invited me to our team workspace last week but when I click the link it says the invitation has expired. We're on the {tier} plan. Can you resend?",
            "priority_bias": "medium",
        },
        {
            "subject": "SSO integration broken after company migration",
            "body": "Our company recently migrated to a new identity provider and now none of our {count} users can log in via SSO. This is blocking all our work. We're an enterprise customer.",
            "priority_bias": "critical",
        },
    ],
    "billing": [
        {
            "subject": "Charged twice this month",
            "body": "I noticed I was billed twice for my {tier} subscription this month — once on the 1st and again on the 15th. My card ending in {card} was charged ${amount} both times. Please refund the duplicate.",
            "priority_bias": "high",
        },
        {
            "subject": "How do I upgrade my plan?",
            "body": "I'm currently on the {tier} plan and I'd like to upgrade to see the pricing and features. I tried the billing page but I can't find an upgrade button. Can you walk me through it?",
            "priority_bias": "low",
        },
        {
            "subject": "Invoice not reflecting discount code",
            "body": "I used discount code SAVE20 when signing up but my first invoice shows the full price of ${amount}. Can you apply the discount retroactively?",
            "priority_bias": "medium",
        },
        {
            "subject": "Need to cancel subscription",
            "body": "Unfortunately I need to cancel my subscription. I've been on the {tier} plan for {months} months but the project it was for has ended. How do I cancel and will I be refunded for the remaining days?",
            "priority_bias": "medium",
        },
        {
            "subject": "Unexpected charge on my account",
            "body": "There's a charge of ${amount} on my credit card from your service but I don't recognize it. My account email is {email}. Can you tell me what this was for?",
            "priority_bias": "high",
        },
        {
            "subject": "Need an invoice for tax purposes",
            "body": "I need a proper VAT invoice for my subscription payments for the last {months} months for my company's accounting. The standard receipts don't have the VAT number. How can I get proper invoices?",
            "priority_bias": "low",
        },
    ],
    "technical_bug": [
        {
            "subject": "Export to CSV is downloading an empty file",
            "body": "Whenever I try to export my data to CSV from the dashboard, I get an empty file. I'm on Chrome {version} on Windows 11. This started happening 3 days ago. The export worked fine before.",
            "priority_bias": "high",
        },
        {
            "subject": "API returning 500 errors intermittently",
            "body": "Our integration is getting random 500 errors from the /api/v2/data endpoint. It's happening about 10% of requests. We're on the enterprise plan and this is affecting our production system. Request IDs: {request_id}",
            "priority_bias": "critical",
        },
        {
            "subject": "Dashboard charts not loading",
            "body": "The analytics charts on my dashboard are showing a loading spinner but never actually loading. This has been happening for 2 days. I've tried clearing cache and different browsers.",
            "priority_bias": "medium",
        },
        {
            "subject": "Mobile app crashing on startup",
            "body": "The iOS app crashes immediately after the splash screen. I'm on iPhone 15 running iOS 17.2 and have the latest version {version} of the app. I've tried reinstalling.",
            "priority_bias": "high",
        },
        {
            "subject": "Email notifications stopped arriving",
            "body": "I stopped receiving email notifications for new activity about a week ago. I checked settings and everything looks correct. I've also verified they're not in spam. My notification settings show email is enabled.",
            "priority_bias": "medium",
        },
        {
            "subject": "Search returning wrong results",
            "body": "The search feature is returning completely unrelated results. When I search for '{search_term}' I get results about something totally different. This makes the product unusable for me.",
            "priority_bias": "high",
        },
        {
            "subject": "File upload fails for files over 5MB",
            "body": "I can't upload files larger than about 5MB even though my plan should allow up to 50MB. The upload bar gets to 100% then shows 'Upload failed'. I need to upload a {size}MB file urgently.",
            "priority_bias": "high",
        },
    ],
    "feature_request": [
        {
            "subject": "Request: Dark mode for the web app",
            "body": "It would be great to have a dark mode option. I use the platform for many hours and the bright interface causes eye strain. Many competitors offer this. Is it on your roadmap?",
            "priority_bias": "low",
        },
        {
            "subject": "Can you add Slack integration?",
            "body": "Our team uses Slack for everything. It would be incredibly useful to get notifications and be able to trigger actions from Slack. We'd definitely upgrade to a higher plan if this was available.",
            "priority_bias": "medium",
        },
        {
            "subject": "Bulk import from CSV",
            "body": "I need to import {count} records but can only add them one by one. A CSV import feature would save me hours of work. Do you have this feature hidden somewhere or is it planned?",
            "priority_bias": "medium",
        },
        {
            "subject": "API rate limit increase request",
            "body": "We're hitting the {limit} requests/minute API rate limit during peak hours. We're an enterprise customer and need a higher limit. Can we discuss a custom rate limit?",
            "priority_bias": "high",
        },
        {
            "subject": "Request: Custom report templates",
            "body": "I generate the same monthly report format for my clients every month. It would save huge amounts of time to have a template system. Is this something you're planning?",
            "priority_bias": "low",
        },
    ],
    "general_inquiry": [
        {
            "subject": "What are the differences between plans?",
            "body": "I'm evaluating your platform for my company of {count} people. Can you explain the main differences between the Pro and Enterprise plans? Specifically interested in user limits, API access, and support SLAs.",
            "priority_bias": "low",
        },
        {
            "subject": "Do you offer a student/nonprofit discount?",
            "body": "I work for a nonprofit organization. Do you offer any discounted pricing for nonprofits? We have a very limited budget but your tool would be perfect for our needs.",
            "priority_bias": "low",
        },
        {
            "subject": "How long is data retained?",
            "body": "I couldn't find information about your data retention policy in the docs. How long is user data kept after account deletion? This is important for our compliance requirements.",
            "priority_bias": "medium",
        },
        {
            "subject": "Is HIPAA compliance available?",
            "body": "We're a healthcare company and need HIPAA compliance for any tools we use. Does your Enterprise plan include a BAA? We're potentially a large customer.",
            "priority_bias": "high",
        },
        {
            "subject": "Where can I find API documentation?",
            "body": "I'm a developer trying to integrate your service. The link in the dashboard to API docs seems broken. Where can I find the full API documentation?",
            "priority_bias": "low",
        },
    ],
}

RESOLUTIONS = {
    "account_access": [
        "Account unlocked and password reset email sent. Customer should receive it within 5 minutes.",
        "SSO configuration updated. Customer tested and confirmed access restored.",
        "2FA backup codes issued. Customer advised to save codes securely.",
    ],
    "billing": [
        "Duplicate charge refunded. Will appear on statement within 3-5 business days.",
        "Discount applied retroactively. Updated invoice sent to customer email.",
        "Subscription cancelled and prorated refund issued.",
    ],
    "technical_bug": [
        "Bug confirmed and escalated to engineering. Fix deployed in version 2.4.1.",
        "Cache issue identified. Customer's cache cleared on our end. Issue resolved.",
        "Intermittent issue traced to database replica lag. Infrastructure team notified.",
    ],
    "feature_request": [
        "Feature request logged in our product backlog. Will notify customer when available.",
        "Feature exists — customer guided to Settings > Integrations. Issue resolved.",
    ],
    "general_inquiry": [
        "Full pricing breakdown sent via email with comparison table.",
        "Documentation link corrected. Customer confirmed access.",
        "Compliance documentation shared under NDA. Next steps: schedule call.",
    ],
}


def random_date(days_back: int = 90) -> str:
    """Generate a random ISO datetime within the last N days."""
    now = datetime.now(timezone.utc)
    offset = timedelta(days=random.randint(0, days_back), hours=random.randint(0, 23))
    return (now - offset).isoformat()


def make_customer():
    """Generate a random customer dict."""
    first = random.choice(FIRST_NAMES)
    last = random.choice(LAST_NAMES)
    name = f"{first} {last}"
    domain = random.choice(EMAIL_DOMAINS)
    email = f"{first.lower()}.{last.lower()}{random.randint(1, 99)}@{domain}"
    return {
        "id": str(uuid.uuid4()),
        "name": name,
        "email": email,
        "subscription_tier": random.choice(SUBSCRIPTION_TIERS),
        "account_status": random.choices(
            ["active", "suspended", "trial"], weights=[0.80, 0.10, 0.10]
        )[0],
    }


def fill_template(template: str, customer: dict) -> str:
    """Replace template placeholders with realistic values."""
    replacements = {
        "{email}": customer["email"],
        "{tier}": customer["subscription_tier"],
        "{months}": str(random.randint(1, 24)),
        "{count}": str(random.randint(5, 500)),
        "{card}": str(random.randint(1000, 9999)),
        "{amount}": str(random.randint(29, 299)),
        "{version}": f"{random.randint(100, 130)}.0.{random.randint(1000, 9999)}",
        "{request_id}": f"req_{uuid.uuid4().hex[:12]}",
        "{search_term}": random.choice(["project alpha", "Q4 report", "user settings", "API key"]),
        "{size}": str(random.randint(6, 45)),
        "{limit}": str(random.choice([100, 500, 1000, 5000])),
    }
    result = template
    for placeholder, value in replacements.items():
        result = result.replace(placeholder, value)
    return result


def generate_tickets(num: int) -> list[dict]:
    """Generate `num` realistic support tickets."""
    tickets = []
    for i in range(num):
        category = random.choice(CATEGORIES)
        templates = TICKET_TEMPLATES[category]
        template = random.choice(templates)
        customer = make_customer()

        # Use the template's priority bias but add some randomness
        bias = template.get("priority_bias", "medium")
        # 70% chance to use the biased priority, 30% random
        if random.random() < 0.70:
            priority = bias
        else:
            priority = random.choices(PRIORITIES, weights=PRIORITY_WEIGHTS)[0]

        status = random.choices(STATUSES, weights=STATUS_WEIGHTS)[0]
        created_at = random_date(90)

        resolution = None
        agent_notes = None
        if status == "resolved":
            resolution = random.choice(RESOLUTIONS.get(category, ["Issue resolved."]))
            agent_notes = f"Auto-resolved by triage agent. Confidence: {random.randint(70, 99)}%"

        ticket = {
            "id": str(uuid.uuid4()),
            "created_at": created_at,
            "customer_id": customer["id"],
            "customer_name": customer["name"],
            "email": customer["email"],
            "subscription_tier": customer["subscription_tier"],
            "subject": fill_template(template["subject"], customer),
            "body": fill_template(template["body"], customer),
            "category": category,
            "priority": priority,
            "status": status,
            "resolution": resolution,
            "agent_notes": agent_notes,
        }
        tickets.append(ticket)

    return tickets


# ──────────────────────────────────────────────────────────────
# Knowledge Base Articles
# ──────────────────────────────────────────────────────────────

KB_ARTICLES = [
    # ── Password Reset / Account Access ──────────────────────
    {
        "title": "How to Reset Your Password",
        "category": "account_access",
        "tags": ["password", "reset", "login", "forgot"],
        "content": """
## How to Reset Your Password

If you've forgotten your password or need to reset it for security reasons, follow these steps:

### Steps to Reset Your Password
1. Go to the login page and click **"Forgot Password"**
2. Enter the email address associated with your account
3. Check your inbox for a password reset email (check spam if not received within 5 minutes)
4. Click the secure link in the email — it expires after 24 hours
5. Enter and confirm your new password
6. Log in with your new password

### Password Requirements
- Minimum 8 characters
- At least one uppercase letter
- At least one number or special character

### Didn't Receive the Email?
- Check your spam/junk folder
- Ensure you're using the email address on your account
- Add noreply@ourplatform.com to your contacts
- Wait 5 minutes and try again
- Contact support if still not received after 15 minutes

### Locked Out?
If your account is locked after too many failed attempts, it will automatically unlock after 30 minutes. Contact support for immediate assistance.
        """.strip(),
    },
    {
        "title": "Setting Up Two-Factor Authentication (2FA)",
        "category": "account_access",
        "tags": ["2fa", "authenticator", "security", "mfa"],
        "content": """
## Setting Up Two-Factor Authentication (2FA)

Two-factor authentication adds an extra layer of security to your account.

### Supported 2FA Methods
- **Authenticator App** (recommended): Google Authenticator, Authy, 1Password
- **SMS**: Text message to your phone number
- **Email OTP**: One-time code to your email

### Setting Up an Authenticator App
1. Go to **Account Settings → Security**
2. Click **Enable Two-Factor Authentication**
3. Choose **Authenticator App**
4. Scan the QR code with your authenticator app
5. Enter the 6-digit code from the app to confirm
6. **Save your backup codes** in a secure location

### If You Lost Access to Your Authenticator
1. Use one of your backup codes to log in
2. Go to Security Settings and disable 2FA
3. Re-enable 2FA with your new device

### If You Lost Both the App and Backup Codes
Contact support with:
- Proof of identity (government ID)
- Account ownership verification (last payment method)
We can manually disable 2FA within 1 business day.
        """.strip(),
    },
    {
        "title": "Troubleshooting Login Issues",
        "category": "account_access",
        "tags": ["login", "access", "troubleshooting", "credentials"],
        "content": """
## Troubleshooting Login Issues

### Common Login Problems and Solutions

**"Invalid email or password" error**
- Double-check you're using the correct email address
- Passwords are case-sensitive — check Caps Lock
- Try copy-pasting instead of typing
- Reset your password if unsure

**Account locked**
- Wait 30 minutes for automatic unlock
- Contact support for immediate unlock

**SSO (Single Sign-On) not working**
- Contact your IT administrator — this is usually a configuration issue
- Ensure you're using your company email address
- Check if your company's SSO provider has an outage

**"Too many requests" error**
- Wait 5 minutes and try again
- This is a rate limit to prevent brute force attacks

**Browser issues**
- Clear browser cache and cookies
- Try an incognito/private window
- Try a different browser (Chrome, Firefox, Safari, Edge)
- Disable browser extensions temporarily

### Still Having Issues?
Contact support with:
- Your account email address
- The exact error message you're seeing
- Browser and operating system version
- Screenshot of the error if possible
        """.strip(),
    },
    {
        "title": "Managing Team Members and Permissions",
        "category": "account_access",
        "tags": ["team", "members", "permissions", "invite", "roles"],
        "content": """
## Managing Team Members and Permissions

### Inviting New Team Members
1. Go to **Settings → Team Members**
2. Click **Invite Member**
3. Enter their email address
4. Select their role (see below)
5. Click **Send Invitation**

The invitation link expires after 7 days.

### Team Roles
| Role | Description |
|------|-------------|
| Owner | Full access, billing control, can delete account |
| Admin | Full access except billing and account deletion |
| Editor | Create and edit content, cannot manage team |
| Viewer | Read-only access |

### Removing Team Members
1. Go to **Settings → Team Members**
2. Find the member
3. Click the three-dot menu → **Remove**
4. Removed members lose access immediately

### Resending Invitations
If an invitation expired, go to **Settings → Pending Invitations** and click **Resend**.

### Plan Limits
- Free: 1 member
- Starter: 5 members
- Pro: 25 members
- Enterprise: Unlimited
        """.strip(),
    },
    {
        "title": "Understanding SSO Configuration",
        "category": "account_access",
        "tags": ["sso", "saml", "okta", "azure", "enterprise"],
        "content": """
## Single Sign-On (SSO) Configuration Guide

SSO is available on Enterprise plans. Supported providers: Okta, Azure AD, Google Workspace, and any SAML 2.0 provider.

### Initial Setup (Enterprise Admins)
1. Go to **Settings → Security → SSO**
2. Select your identity provider
3. Download our SAML metadata or copy the Entity ID and ACS URL
4. Configure in your identity provider using our metadata
5. Enter your identity provider's metadata URL or upload their metadata XML
6. Test the connection using the **Test SSO** button
7. Enable for all users or specific groups

### Troubleshooting SSO
- **"SAML assertion expired"**: Check that server times are synchronized (NTP)
- **"User not found"**: Ensure the email in the SAML assertion matches an account
- **"Invalid signature"**: Re-download and re-upload certificates
- **"Redirect loop"**: Clear cookies and try again

### Emergency Access
If SSO is broken, owners can use email/password login at `/login?bypass-sso=true` (uses magic link).
        """.strip(),
    },
    # ── Billing ─────────────────────────────────────────────
    {
        "title": "Understanding Your Invoice",
        "category": "billing",
        "tags": ["invoice", "billing", "receipt", "charges"],
        "content": """
## Understanding Your Invoice

### Invoice Sections
- **Subscription**: Your base plan cost (billed monthly or annually)
- **Usage**: Any metered usage above your plan limits
- **Tax**: Applicable sales tax based on your billing address
- **Discounts**: Any promo codes or loyalty discounts applied

### Billing Dates
Your billing date is the date you originally subscribed. Annual plans are billed once per year on that date.

### How to Download Invoices
1. Go to **Settings → Billing**
2. Click **Billing History**
3. Click the download icon next to any invoice

### VAT/GST Invoices
If you need a tax invoice for business purposes:
1. Go to **Settings → Billing → Tax Information**
2. Enter your VAT/GST number and business address
3. Future invoices will include this information
4. Contact support to reissue past invoices

### Currency
We bill in USD by default. Enterprise customers can request local currency billing. Exchange rates are fixed at the start of each annual term.
        """.strip(),
    },
    {
        "title": "How Billing Works: Plans and Upgrades",
        "category": "billing",
        "tags": ["upgrade", "downgrade", "plan", "pricing"],
        "content": """
## How Billing Works: Plans and Upgrades

### Plan Overview
| Plan | Monthly | Annual | Users | Features |
|------|---------|--------|-------|----------|
| Free | $0 | $0 | 1 | Basic features |
| Starter | $29 | $290 | 5 | + Integrations |
| Pro | $79 | $790 | 25 | + Advanced analytics |
| Enterprise | Custom | Custom | Unlimited | + SLA, SSO, custom |

### Upgrading Your Plan
1. Go to **Settings → Billing → Change Plan**
2. Select the new plan
3. Confirm the change

When you upgrade mid-cycle, you're charged the prorated difference immediately.

### Downgrading Your Plan
Downgrades take effect at the end of your current billing cycle. You keep your current features until then.

If downgrading would put you over the new plan's limits (e.g., too many users), you'll need to reduce usage first.

### Annual vs Monthly Billing
Annual billing saves ~17% compared to monthly. You can switch from monthly to annual at any time — we'll credit unused monthly days.

### Free Trial
New accounts get 14 days free on the Pro plan. No credit card required. After the trial, you'll move to Free unless you add payment details.
        """.strip(),
    },
    {
        "title": "Requesting a Refund",
        "category": "billing",
        "tags": ["refund", "cancel", "money back", "charge"],
        "content": """
## Requesting a Refund

### Refund Policy
- **Annual plans**: Refundable within 30 days of purchase (prorated for usage)
- **Monthly plans**: Current month is non-refundable; cancel to stop future charges
- **Duplicate charges**: Refunded immediately upon verification
- **Accidental upgrades**: Refundable within 48 hours

### How to Request a Refund
Contact support with:
1. Your account email
2. The charge amount and date
3. Reason for the refund request
4. For duplicate charges: last 4 digits of the card charged

### Processing Time
- Credit/debit cards: 5-10 business days
- PayPal: 3-5 business days
- Wire transfer: 10-15 business days

### Cancellation
To stop future charges, cancel your subscription before the next renewal date:
1. Go to **Settings → Billing → Cancel Subscription**
2. Select a reason (optional)
3. Confirm cancellation

Your access continues until the end of the paid period.
        """.strip(),
    },
    {
        "title": "Payment Methods and Updating Billing Info",
        "category": "billing",
        "tags": ["payment", "credit card", "update", "billing"],
        "content": """
## Payment Methods and Updating Billing Info

### Accepted Payment Methods
- Credit/debit cards: Visa, Mastercard, American Express, Discover
- PayPal (monthly plans only)
- Wire transfer (Enterprise annual plans only)
- Purchase orders (Enterprise only)

### Updating Your Credit Card
1. Go to **Settings → Billing → Payment Method**
2. Click **Update Card**
3. Enter new card details
4. Click **Save**

Changes take effect on the next billing cycle. Past invoices remain unchanged.

### Failed Payment Recovery
If a payment fails:
1. You'll receive an email notification
2. We retry the charge after 3 days
3. If the second attempt fails, we retry after 7 more days
4. After 3 failed attempts, your account is suspended

During suspension, your data is retained for 30 days while you update payment.

### PCI Compliance
We never store card numbers. Payments are processed by Stripe, a PCI DSS Level 1 certified processor.
        """.strip(),
    },
    # ── Technical / Bugs ────────────────────────────────────
    {
        "title": "Troubleshooting Export Issues",
        "category": "technical_bug",
        "tags": ["export", "csv", "download", "data"],
        "content": """
## Troubleshooting Export Issues

### Common Export Problems

**Empty file downloaded**
1. Ensure there is data matching your current filters
2. Try removing filters and exporting all data
3. Clear browser cache and try again
4. Try a different browser
5. Check if a popup blocker is preventing the download

**Export takes too long or times out**
- Large exports (>10,000 rows) are processed in the background
- You'll receive an email with a download link when ready
- Download links expire after 24 hours

**Wrong data in export**
- Verify the date range and filters before exporting
- Some fields may use internal IDs — refer to the API docs for field mappings
- Timestamps are in UTC by default

**CSV encoding issues**
- Open with Excel: Data → From Text/CSV → select UTF-8 encoding
- Use Google Sheets which handles UTF-8 automatically

### Supported Export Formats
- CSV (all plans)
- JSON (Pro and above)
- Excel/XLSX (Pro and above)
- PDF reports (Enterprise)

### Export Limits
- Free: 1,000 rows
- Starter: 10,000 rows
- Pro: 100,000 rows
- Enterprise: Unlimited (background processing)
        """.strip(),
    },
    {
        "title": "API Error Code Reference",
        "category": "technical_bug",
        "tags": ["api", "error", "500", "400", "integration"],
        "content": """
## API Error Code Reference

### HTTP Status Codes

| Code | Meaning | Common Causes |
|------|---------|---------------|
| 400 | Bad Request | Invalid parameters, missing required fields |
| 401 | Unauthorized | Missing or invalid API key |
| 403 | Forbidden | API key lacks permission for this endpoint |
| 404 | Not Found | Resource doesn't exist or was deleted |
| 429 | Too Many Requests | Rate limit exceeded |
| 500 | Internal Server Error | Temporary server issue |
| 503 | Service Unavailable | Planned maintenance or incident |

### Rate Limits
| Plan | Requests/minute | Requests/day |
|------|-----------------|--------------|
| Free | 30 | 1,000 |
| Starter | 100 | 10,000 |
| Pro | 500 | 100,000 |
| Enterprise | Custom | Custom |

### Handling 429 Rate Limits
Implement exponential backoff:
```python
import time
import random

def api_request_with_retry(url, max_retries=5):
    for attempt in range(max_retries):
        response = make_request(url)
        if response.status_code == 429:
            wait = (2 ** attempt) + random.random()
            time.sleep(wait)
        else:
            return response
```

### Handling 500 Errors
- 500s are transient — retry with backoff
- If consistently failing, check our status page
- Include the `X-Request-ID` header value when contacting support
        """.strip(),
    },
    {
        "title": "Browser Compatibility and Troubleshooting",
        "category": "technical_bug",
        "tags": ["browser", "chrome", "firefox", "safari", "compatibility"],
        "content": """
## Browser Compatibility and Troubleshooting

### Supported Browsers
| Browser | Minimum Version |
|---------|-----------------|
| Chrome | 90+ |
| Firefox | 88+ |
| Safari | 14+ |
| Edge | 90+ |

Internet Explorer is not supported.

### General Troubleshooting Steps
1. **Hard refresh**: Ctrl+Shift+R (Windows) or Cmd+Shift+R (Mac)
2. **Clear cache and cookies**:
   - Chrome: Settings → Privacy → Clear browsing data
   - Firefox: Settings → Privacy → Clear Data
   - Safari: Develop menu → Empty Caches
3. **Try incognito/private mode** to rule out extension conflicts
4. **Disable extensions** temporarily (especially ad blockers)
5. **Check browser console** (F12 → Console) for error messages

### Common Issues

**Blank/white page**
- Usually a JavaScript error — check console for details
- Disable extensions, especially ad blockers and script blockers

**Infinite loading spinner**
- Check network status (F12 → Network tab)
- If requests are failing, may be a firewall/proxy issue

**Features not working properly**
- Enable JavaScript and cookies
- Ensure browser is updated to latest version

### Corporate Networks
Some corporate firewalls block certain CDN domains. Whitelist:
- `*.ourplatform.com`
- `*.cloudfront.net`
- `*.stripe.com` (for billing)
        """.strip(),
    },
    {
        "title": "Mobile App Troubleshooting",
        "category": "technical_bug",
        "tags": ["mobile", "ios", "android", "app", "crash"],
        "content": """
## Mobile App Troubleshooting

### Supported OS Versions
- iOS: 15.0 and above
- Android: 9.0 (API 28) and above

### Common Issues

**App crashes on startup**
1. Force-close the app and reopen
2. Check for updates in the App Store / Google Play
3. Restart your device
4. Uninstall and reinstall the app
5. Ensure you have at least 500MB free storage

**Can't log in on mobile**
- Ensure you're entering the correct email (no extra spaces from autocomplete)
- Try logging in from the web to verify credentials
- If using Face ID/Touch ID, go to Settings → Biometrics and re-enable

**Notifications not arriving**
- Check notification permissions: Device Settings → App Name → Notifications → Allow
- Ensure Do Not Disturb is not enabled
- Go to app Settings → Notifications and verify preferences

**Sync issues / outdated data**
- Pull down to refresh in any list view
- Go to Settings → Account → Force Sync

**Push notifications duplicated**
- Log out and log back in to refresh the device token
        """.strip(),
    },
    # ── Feature Guides ───────────────────────────────────────
    {
        "title": "Getting Started: Quick Setup Guide",
        "category": "general_inquiry",
        "tags": ["getting started", "setup", "onboarding", "new user"],
        "content": """
## Getting Started: Quick Setup Guide

Welcome! Here's how to get up and running in 10 minutes.

### Step 1: Complete Your Profile
1. Click your avatar in the top right
2. Go to **Profile Settings**
3. Add your name, photo, and timezone
4. Save changes

### Step 2: Set Up Your Workspace
1. Go to **Settings → General**
2. Name your workspace
3. Upload a logo (optional)
4. Set your timezone

### Step 3: Connect Integrations
1. Go to **Settings → Integrations**
2. Connect your email (Gmail, Outlook)
3. Connect Slack for notifications
4. Connect your CRM if applicable

### Step 4: Invite Your Team
1. Go to **Settings → Team**
2. Click **Invite Members**
3. Enter email addresses and assign roles

### Step 5: Import Your Data
1. Use **File → Import** for CSV imports
2. Or use our API for bulk imports
3. See the import guide for field mappings

### Helpful Resources
- [Video tutorials](https://help.ourplatform.com/videos)
- [API documentation](https://api.ourplatform.com/docs)
- [Community forum](https://community.ourplatform.com)
        """.strip(),
    },
    {
        "title": "Data Privacy and GDPR Compliance",
        "category": "general_inquiry",
        "tags": ["gdpr", "privacy", "data", "compliance", "security"],
        "content": """
## Data Privacy and GDPR Compliance

### Our Commitment to Privacy
We are fully GDPR compliant and take data privacy seriously. Our DPA (Data Processing Agreement) is available upon request.

### Data Storage
- All data is stored in EU data centers (AWS eu-west-1) by default
- US region available for Enterprise customers
- Data is encrypted at rest (AES-256) and in transit (TLS 1.3)

### Data Retention
| Scenario | Retention Period |
|----------|-----------------|
| Active accounts | Indefinitely |
| After account deletion | 30 days (then permanently deleted) |
| Backup data | 90 days |
| Audit logs | 12 months |

### Your Rights
Under GDPR, you have the right to:
- **Access**: Request a copy of all your data
- **Erasure**: Request deletion of your data
- **Portability**: Export your data in machine-readable format
- **Rectification**: Correct inaccurate data
- **Objection**: Object to certain types of processing

### Exercising Your Rights
Go to **Settings → Privacy** or contact privacy@ourplatform.com.

### Security Measures
- SOC 2 Type II certified
- Annual penetration testing
- Bug bounty program
- 24/7 security monitoring
        """.strip(),
    },
    {
        "title": "Enterprise Plan: Features and Onboarding",
        "category": "general_inquiry",
        "tags": ["enterprise", "plan", "features", "sla", "custom"],
        "content": """
## Enterprise Plan: Features and Onboarding

### Enterprise Features
- **Unlimited users** with advanced role management
- **SSO/SAML**: Okta, Azure AD, Google Workspace, any SAML 2.0 provider
- **Dedicated support**: Named support engineer, 4-hour SLA
- **Custom rate limits** for API usage
- **Data residency**: Choose EU or US storage
- **Audit logs**: Full activity log with export
- **Custom contract**: MSA, DPA, custom terms
- **HIPAA BAA**: Available for healthcare customers
- **SLA guarantee**: 99.9% uptime with financial credits

### Pricing
Enterprise pricing is custom based on:
- Number of users
- API usage volume
- Contract length (annual minimum)
- Additional features needed

### Onboarding Process
1. **Discovery call** (30 min): Understand your needs
2. **Technical review** (60 min): Architecture review with our solutions engineer
3. **Security review**: Share our SOC2 report and complete your security questionnaire
4. **Pilot** (2 weeks): Full-access trial for your team
5. **Contract and migration**: Data migration assistance included

### Getting Started
Contact enterprise@ourplatform.com or book a call through the website. We typically respond within 2 hours on business days.
        """.strip(),
    },
    {
        "title": "API Authentication and Getting Started",
        "category": "general_inquiry",
        "tags": ["api", "authentication", "token", "developer", "integration"],
        "content": """
## API Authentication and Getting Started

### API Base URL
```
https://api.ourplatform.com/v2
```

### Authentication
All API requests require an API key in the Authorization header:
```http
Authorization: Bearer YOUR_API_KEY
```

### Getting Your API Key
1. Go to **Settings → API Keys**
2. Click **Generate New Key**
3. Give it a descriptive name (e.g., "Production Integration")
4. Copy the key immediately — it's only shown once
5. Store it securely (use a secrets manager in production)

### Quick Start Example
```python
import requests

API_KEY = "your_api_key_here"
BASE_URL = "https://api.ourplatform.com/v2"

headers = {"Authorization": f"Bearer {API_KEY}"}

# Get all records
response = requests.get(f"{BASE_URL}/records", headers=headers)
data = response.json()
print(data)
```

### API Documentation
Full interactive documentation available at: https://api.ourplatform.com/docs

### Webhooks
Receive real-time notifications for events:
1. Go to **Settings → Webhooks**
2. Enter your endpoint URL
3. Select events to subscribe to
4. We'll send a POST request with a JSON payload for each event

### SDKs Available
- Python: `pip install ourplatform-sdk`
- JavaScript/Node.js: `npm install @ourplatform/sdk`
- Ruby, PHP, Go: Coming soon
        """.strip(),
    },
]


# Add more KB articles to reach 50
ADDITIONAL_KB_ARTICLES = [
    {
        "title": "How to Use the Search Feature",
        "category": "general_inquiry",
        "tags": ["search", "filter", "find"],
        "content": "Use the search bar at the top of any page to search across all your data. Use filters to narrow results by date, type, status, and more. Supports full-text search and exact phrase matching with quotes.",
    },
    {
        "title": "Keyboard Shortcuts Reference",
        "category": "general_inquiry",
        "tags": ["keyboard", "shortcuts", "productivity"],
        "content": "Press ? on any page to view keyboard shortcuts. Common shortcuts: Ctrl/Cmd+K (quick search), Ctrl/Cmd+N (new item), Ctrl/Cmd+S (save), Escape (close modal/dialog).",
    },
    {
        "title": "Exporting Your Data Before Cancellation",
        "category": "billing",
        "tags": ["export", "cancel", "data portability", "migration"],
        "content": "Before cancelling your account, export all your data from Settings → Export Data. You can export everything as a ZIP file containing CSV files for each data type. After cancellation, data is available for 30 days for download before permanent deletion.",
    },
    {
        "title": "Connecting Gmail for Email Integration",
        "category": "general_inquiry",
        "tags": ["gmail", "email", "integration", "google"],
        "content": "Go to Settings → Integrations → Gmail and click Connect. Sign in with your Google account and grant the requested permissions. Once connected, emails can be automatically captured. Disconnect anytime from the same settings page.",
    },
    {
        "title": "Setting Up Slack Notifications",
        "category": "general_inquiry",
        "tags": ["slack", "notifications", "integration", "alerts"],
        "content": "Go to Settings → Integrations → Slack. Click Add to Slack. Select the workspace and channel for notifications. Choose which event types trigger notifications. You can configure per-workspace settings for teams.",
    },
    {
        "title": "Understanding User Roles and Permissions",
        "category": "account_access",
        "tags": ["roles", "permissions", "admin", "access control"],
        "content": "Roles: Owner (full access), Admin (full except billing/deletion), Editor (create and edit), Viewer (read-only). Roles can be changed by Owners and Admins from Settings → Team Members. Custom roles available on Enterprise plans.",
    },
    {
        "title": "Using the Dashboard and Analytics",
        "category": "general_inquiry",
        "tags": ["dashboard", "analytics", "reports", "metrics"],
        "content": "The dashboard shows key metrics from the last 30 days by default. Use the date picker to change the range. Click any metric to see a detailed breakdown. Dashboard widgets can be rearranged and customized. Enterprise plans get custom dashboard creation.",
    },
    {
        "title": "Data Import: CSV Format Requirements",
        "category": "technical_bug",
        "tags": ["import", "csv", "data", "format", "migration"],
        "content": "CSV imports require UTF-8 encoding. First row must be headers matching field names from the API docs. Required fields: email, name. Optional: all other fields. Maximum 50,000 rows per import. For larger imports use the API. Template available at Settings → Import → Download Template.",
    },
    {
        "title": "Webhook Setup and Troubleshooting",
        "category": "technical_bug",
        "tags": ["webhook", "api", "integration", "events"],
        "content": "Webhooks send POST requests to your endpoint for configured events. Your endpoint must return 200 within 10 seconds. Failed deliveries are retried 3 times with exponential backoff. View delivery logs in Settings → Webhooks → Delivery Logs. Verify webhook signatures using the secret key in your headers.",
    },
    {
        "title": "Account Deletion and Data Removal",
        "category": "account_access",
        "tags": ["delete", "close", "account", "removal"],
        "content": "To delete your account: Settings → Account → Delete Account. Only the Owner can delete the account. This action cannot be undone. All data is permanently deleted within 30 days. Export your data first. Deleting the account cancels the subscription with no refund of the current period.",
    },
    {
        "title": "Troubleshooting Sync Issues",
        "category": "technical_bug",
        "tags": ["sync", "data", "refresh", "update"],
        "content": "If data seems outdated: 1) Hard refresh the browser (Ctrl+Shift+R), 2) Log out and back in, 3) Go to Settings → Advanced → Force Sync. Sync issues are often due to network interruptions. Check our status page if the problem persists.",
    },
    {
        "title": "Understanding API Rate Limits",
        "category": "technical_bug",
        "tags": ["api", "rate limit", "429", "throttle"],
        "content": "Rate limits apply per API key. When exceeded, the API returns 429 Too Many Requests with a Retry-After header indicating seconds to wait. Implement exponential backoff. Check X-RateLimit-Remaining header to monitor usage. Enterprise customers can request higher limits.",
    },
    {
        "title": "Setting Up SAML SSO with Okta",
        "category": "account_access",
        "tags": ["sso", "okta", "saml", "enterprise"],
        "content": "1) In our platform: Settings → SSO → Enable SAML → download metadata. 2) In Okta: Applications → Add Application → SAML 2.0 → upload our metadata. 3) Copy Okta's metadata URL and paste into our SSO settings. 4) Test with the Test SSO button. 5) Enable for your users.",
    },
    {
        "title": "How Annual Billing Proration Works",
        "category": "billing",
        "tags": ["annual", "proration", "billing", "upgrade"],
        "content": "When upgrading mid-annual-term: you're charged the prorated difference for the remaining days times the price difference. When downgrading: no refund, change takes effect at renewal. Switching from monthly to annual: remaining monthly days are credited. All proration is calculated by day.",
    },
    {
        "title": "Setting Up IP Allowlisting",
        "category": "account_access",
        "tags": ["ip", "whitelist", "allowlist", "security", "enterprise"],
        "content": "Enterprise plan feature. Go to Settings → Security → IP Allowlist. Add trusted IP ranges in CIDR notation. Once enabled, logins from other IPs are blocked. Always add your own IP first. Emergency bypass: contact support. Recommended for high-security environments.",
    },
    {
        "title": "Using the Audit Log",
        "category": "account_access",
        "tags": ["audit", "log", "activity", "history", "enterprise"],
        "content": "Enterprise feature. Go to Settings → Audit Log to see all account activity. Filterable by user, action type, and date range. Events include logins, data changes, settings updates, and API access. Can be exported as CSV. Retained for 12 months. Useful for compliance and security reviews.",
    },
    {
        "title": "Troubleshooting Email Notifications",
        "category": "technical_bug",
        "tags": ["email", "notifications", "alerts", "spam"],
        "content": "If not receiving emails: 1) Check spam/junk folder, 2) Add noreply@ourplatform.com to contacts, 3) Verify notification settings at Settings → Notifications, 4) Check if email is verified under Account Settings, 5) Contact support if the issue persists for more than 24 hours.",
    },
    {
        "title": "Upgrading from Free to Paid Plans",
        "category": "billing",
        "tags": ["upgrade", "free", "paid", "starter", "pro"],
        "content": "To upgrade: Settings → Billing → Upgrade Plan. Add a payment method if not already on file. Select your desired plan and billing frequency (monthly saves flexibility, annual saves money). The upgrade takes effect immediately — you keep your data and settings.",
    },
    {
        "title": "Setting Up Custom Domains",
        "category": "general_inquiry",
        "tags": ["custom domain", "branding", "white label", "pro"],
        "content": "Pro and Enterprise feature. Go to Settings → Custom Domain. Enter your domain. Add the required CNAME record to your DNS. Wait up to 48 hours for DNS propagation. SSL certificate is automatically provisioned. Custom login page and branded emails available.",
    },
    {
        "title": "Understanding Storage Limits",
        "category": "general_inquiry",
        "tags": ["storage", "limits", "file", "quota"],
        "content": "Storage limits by plan: Free 1GB, Starter 10GB, Pro 100GB, Enterprise unlimited. View usage at Settings → Storage. Files over the limit cannot be uploaded. You'll receive email alerts at 80% and 95% capacity. Upgrade anytime to increase storage. Old or unused files can be deleted to free space.",
    },
]

KB_ARTICLES.extend(ADDITIONAL_KB_ARTICLES)


def generate_kb_articles(articles: list[dict]) -> list[dict]:
    """Add IDs and timestamps to KB articles."""
    result = []
    for i, article in enumerate(articles[:NUM_KB_ARTICLES]):
        result.append(
            {
                "id": str(uuid.uuid4()),
                "title": article["title"],
                "category": article["category"],
                "tags": article["tags"],
                "content": article["content"],
                "embedding_id": None,  # Set when indexed into ChromaDB
                "created_at": random_date(180),
                "word_count": len(article["content"].split()),
            }
        )
    return result


def main():
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    print("Generating sample data for the AI Agents Course...")
    print(f"  Output directory: {DATA_DIR.resolve()}")

    # Generate tickets
    print(f"\nGenerating {NUM_TICKETS} support tickets...")
    tickets = generate_tickets(NUM_TICKETS)

    # Stats
    from collections import Counter
    cat_counts = Counter(t["category"] for t in tickets)
    pri_counts = Counter(t["priority"] for t in tickets)
    sta_counts = Counter(t["status"] for t in tickets)

    print(f"  Categories: {dict(cat_counts)}")
    print(f"  Priorities: {dict(pri_counts)}")
    print(f"  Statuses:   {dict(sta_counts)}")

    TICKETS_FILE.write_text(json.dumps(tickets, indent=2, ensure_ascii=False))
    print(f"  Saved: {TICKETS_FILE}")

    # Generate KB articles
    print(f"\nGenerating {NUM_KB_ARTICLES} knowledge base articles...")
    kb_articles = generate_kb_articles(KB_ARTICLES)
    kb_cat_counts = Counter(a["category"] for a in kb_articles)
    print(f"  Categories: {dict(kb_cat_counts)}")

    KB_FILE.write_text(json.dumps(kb_articles, indent=2, ensure_ascii=False))
    print(f"  Saved: {KB_FILE}")

    print(f"\nDone! Run python scripts/verify_setup.py to check your environment.")


if __name__ == "__main__":
    main()
