#!/usr/bin/env python3
"""
Google Ads Article Monitor for Search Engine Land
This script scrapes searchengineland.com for Google Ads related articles,
summarizes the top 3 most relevant ones, and emails them with beautiful formatting.
"""

import requests
from bs4 import BeautifulSoup
import google.generativeai as genai
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
import os
import time

# ============================================================================
# CONFIGURATION
# ============================================================================

# Configuration is read from environment variables (GitHub Secrets)
# This keeps your sensitive information secure
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY', 'your_gemini_api_key_here')
GMAIL_ADDRESS = os.environ.get('GMAIL_ADDRESS', 'your_email@gmail.com')
GMAIL_APP_PASSWORD = os.environ.get('GMAIL_APP_PASSWORD', 'your_16_char_app_password')
RECIPIENT_EMAIL = os.environ.get('RECIPIENT_EMAIL', 'your_email@gmail.com')

# Topics to monitor
KEYWORDS = ["google ads", "google advertising", "ppc", "paid search", "google adwords"]

# ============================================================================
# FUNCTIONS
# ============================================================================

def scrape_search_engine_land():
    """
    Scrapes the latest articles from Search Engine Land
    Returns a list of dictionaries with title, url, and snippet
    """
    print("📰 Scraping Search Engine Land...")
    
    url = "https://searchengineland.com/"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, 'html.parser')
        
        articles = []
        
        # Find article elements (Search Engine Land structure)
        # They use article tags with specific classes
        article_elements = soup.find_all('article', limit=30)  # Get more articles to filter from
        
        for article in article_elements:
            # Extract title
            title_tag = article.find(['h2', 'h3', 'h4'])
            if not title_tag:
                continue
                
            title = title_tag.get_text(strip=True)
            
            # Extract link
            link_tag = title_tag.find('a') or article.find('a')
            if not link_tag or not link_tag.get('href'):
                continue
                
            url = link_tag['href']
            
            # Extract snippet/description
            snippet_tag = article.find('p') or article.find('div', class_=['excerpt', 'description'])
            snippet = snippet_tag.get_text(strip=True) if snippet_tag else ""
            
            articles.append({
                'title': title,
                'url': url,
                'snippet': snippet
            })
        
        print(f"✅ Found {len(articles)} articles")
        return articles
        
    except Exception as e:
        print(f"❌ Error scraping website: {e}")
        return []


def filter_relevant_articles(articles):
    """
    Filters articles for Google Ads relevance using AI
    Returns top 3 most relevant articles with relevance scores
    """
    print("🔍 Filtering for Google Ads relevance using AI...")
    
    if not articles:
        return []
    
    # Configure Gemini
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel('gemini-1.5-flash')
    
    # Prepare articles for AI analysis
    articles_text = ""
    for i, article in enumerate(articles[:20], 1):  # Analyze first 20 articles
        articles_text += f"\n{i}. TITLE: {article['title']}\n   SNIPPET: {article['snippet']}\n"
    
    prompt = f"""Analyze these articles from Search Engine Land and identify which ones are most relevant to Google Ads (PPC, paid search, Google advertising).

Articles:
{articles_text}

For each article, rate its relevance to Google Ads on a scale of 0-10:
- 10 = Directly about Google Ads features, updates, strategies, or news
- 7-9 = Heavily related to paid search or PPC
- 4-6 = Mentions Google Ads but focuses on other topics
- 0-3 = Not relevant to Google Ads

Return ONLY a JSON array with the top 3 most relevant articles in this exact format:
[
  {{"number": 1, "score": 10, "reason": "Brief reason"}},
  {{"number": 5, "score": 9, "reason": "Brief reason"}},
  {{"number": 3, "score": 8, "reason": "Brief reason"}}
]"""

    try:
        response = model.generate_content(prompt)
        response_text = response.text
        
        # Parse AI response
        import json
        import re
        json_match = re.search(r'\[.*\]', response_text, re.DOTALL)
        if json_match:
            rankings = json.loads(json_match.group())
            
            # Get the top 3 articles based on AI ranking
            relevant_articles = []
            for rank in rankings[:3]:
                article_index = rank['number'] - 1
                if article_index < len(articles):
                    article = articles[article_index].copy()
                    article['relevance_score'] = rank['score']
                    article['relevance_reason'] = rank['reason']
                    relevant_articles.append(article)
            
            print(f"✅ Found {len(relevant_articles)} relevant articles")
            return relevant_articles
        else:
            print("⚠️  Could not parse AI response, falling back to keyword matching")
            return keyword_filter_fallback(articles)
            
    except Exception as e:
        print(f"⚠️  AI filtering error: {e}, using keyword fallback")
        return keyword_filter_fallback(articles)


def keyword_filter_fallback(articles):
    """
    Fallback method: Filter articles by keywords if AI fails
    """
    relevant = []
    for article in articles:
        text = (article['title'] + ' ' + article['snippet']).lower()
        if any(keyword.lower() in text for keyword in KEYWORDS):
            relevant.append(article)
    return relevant[:3]


def summarize_article(article):
    """
    Fetches the full article content and creates an AI summary
    Returns the summary text
    """
    print(f"📝 Summarizing: {article['title'][:50]}...")
    
    # Configure Gemini
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel('gemini-1.5-flash')
    
    # Fetch full article content
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        response = requests.get(article['url'], headers=headers, timeout=10)
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Remove script and style elements
        for script in soup(["script", "style", "nav", "footer", "header"]):
            script.decompose()
        
        # Get article text
        article_body = soup.find('article') or soup.find('main') or soup.find('body')
        article_text = article_body.get_text(separator='\n', strip=True) if article_body else ""
        
        # Limit text length for API
        article_text = article_text[:8000]
        
    except Exception as e:
        print(f"⚠️  Could not fetch full article, using snippet: {e}")
        article_text = article['snippet']
    
    # Create summary with AI
    prompt = f"""Summarize this article about Google Ads in 3-4 concise bullet points. Focus on:
- Key takeaways for Google Ads marketers
- Important updates or changes
- Actionable insights

Article Title: {article['title']}

Article Content:
{article_text}

Provide a summary in bullet points (use • symbol)."""

    try:
        response = model.generate_content(prompt)
        summary = response.text
        print("✅ Summary created")
        return summary
        
    except Exception as e:
        print(f"❌ Summary error: {e}")
        return f"• {article['snippet']}"


def create_html_email(articles_with_summaries):
    """
    Creates a beautifully formatted HTML email with distinct article sections
    Each article is visually independent with standout titles
    """
    today = datetime.now().strftime("%B %d, %Y")
    
    # Create article HTML blocks
    articles_html = ""
    
    for i, article in enumerate(articles_with_summaries, 1):
        # Different colors for each article to make them distinct
        colors = ["#1a73e8", "#d93025", "#0d9488"]
        color = colors[i % 3]
        
        articles_html += f"""
        <div style="background: white; border-left: 5px solid {color}; padding: 25px; margin-bottom: 30px; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.1);">
            <div style="background: {color}; color: white; padding: 15px 20px; margin: -25px -25px 20px -25px; border-radius: 8px 8px 0 0;">
                <h2 style="margin: 0; font-size: 24px; font-weight: bold; line-height: 1.3;">
                    📌 ARTICLE {i}: {article['title']}
                </h2>
            </div>
            
            <div style="padding: 10px 0;">
                <h3 style="color: #333; font-size: 18px; margin-bottom: 15px; font-weight: 600;">Key Insights:</h3>
                <div style="color: #444; font-size: 15px; line-height: 1.8;">
                    {article['summary']}
                </div>
            </div>
            
            <div style="margin-top: 20px; padding-top: 15px; border-top: 2px solid #eee;">
                <a href="{article['url']}" style="background: {color}; color: white; padding: 12px 24px; text-decoration: none; border-radius: 5px; font-weight: bold; display: inline-block; font-size: 14px;">
                    📖 READ FULL ARTICLE →
                </a>
            </div>
        </div>
        """
    
    # Complete HTML email template
    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
    </head>
    <body style="margin: 0; padding: 0; background-color: #f5f5f5; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
        <div style="max-width: 700px; margin: 0 auto; padding: 20px;">
            
            <!-- Header -->
            <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 40px 30px; border-radius: 12px; text-align: center; margin-bottom: 30px;">
                <h1 style="margin: 0; font-size: 32px; font-weight: bold;">🎯 Your Daily Google Ads Digest</h1>
                <p style="margin: 10px 0 0 0; font-size: 16px; opacity: 0.9;">Top 3 Articles from Search Engine Land</p>
                <p style="margin: 5px 0 0 0; font-size: 14px; opacity: 0.8;">{today}</p>
            </div>
            
            <!-- Articles -->
            {articles_html}
            
            <!-- Footer -->
            <div style="text-align: center; padding: 20px; color: #666; font-size: 13px; border-top: 2px solid #ddd; margin-top: 30px;">
                <p style="margin: 5px 0;">🤖 Powered by AI Article Monitor</p>
                <p style="margin: 5px 0;">Source: <a href="https://searchengineland.com" style="color: #1a73e8;">Search Engine Land</a></p>
            </div>
            
        </div>
    </body>
    </html>
    """
    
    return html


def send_email(html_content):
    """
    Sends the HTML email via Gmail SMTP
    """
    print("📧 Sending email...")
    
    # Create message
    msg = MIMEMultipart('alternative')
    msg['Subject'] = f"🎯 Your Google Ads Digest - {datetime.now().strftime('%b %d, %Y')}"
    msg['From'] = GMAIL_ADDRESS
    msg['To'] = RECIPIENT_EMAIL
    
    # Attach HTML content
    html_part = MIMEText(html_content, 'html')
    msg.attach(html_part)
    
    try:
        # Connect to Gmail SMTP server
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(GMAIL_ADDRESS, GMAIL_APP_PASSWORD)
        server.send_message(msg)
        server.quit()
        
        print("✅ Email sent successfully!")
        return True
        
    except Exception as e:
        print(f"❌ Email error: {e}")
        return False


# ============================================================================
# MAIN EXECUTION
# ============================================================================

def main():
    """
    Main function that orchestrates the entire workflow
    """
    print("\n" + "="*60)
    print("🚀 GOOGLE ADS ARTICLE MONITOR STARTING")
    print("="*60 + "\n")
    
    # Step 1: Scrape articles
    articles = scrape_search_engine_land()
    if not articles:
        print("❌ No articles found. Exiting.")
        return
    
    # Step 2: Filter for relevance
    time.sleep(1)  # Brief pause
    relevant_articles = filter_relevant_articles(articles)
    if not relevant_articles:
        print("❌ No relevant Google Ads articles found today.")
        return
    
    # Step 3: Summarize each article
    articles_with_summaries = []
    for article in relevant_articles:
        time.sleep(1)  # Pause between API calls
        summary = summarize_article(article)
        article['summary'] = summary
        articles_with_summaries.append(article)
    
    # Step 4: Create HTML email
    html_email = create_html_email(articles_with_summaries)
    
    # Step 5: Send email
    send_email(html_email)
    
    print("\n" + "="*60)
    print("✅ PROCESS COMPLETE!")
    print("="*60 + "\n")


if __name__ == "__main__":
    main()
