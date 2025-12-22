/**
 * Website Blocker - Blocked Page Script
 */

// Motivational quotes to display
const quotes = [
    {
        text: "The successful warrior is the average man, with laser-like focus.",
        author: "Bruce Lee"
    },
    {
        text: "Concentrate all your thoughts upon the work at hand. The sun's rays do not burn until brought to a focus.",
        author: "Alexander Graham Bell"
    },
    {
        text: "It is during our darkest moments that we must focus to see the light.",
        author: "Aristotle"
    },
    {
        text: "Focus on being productive instead of busy.",
        author: "Tim Ferriss"
    },
    {
        text: "The main thing is to keep the main thing the main thing.",
        author: "Stephen Covey"
    },
    {
        text: "Where focus goes, energy flows.",
        author: "Tony Robbins"
    },
    {
        text: "You can do anything, but not everything.",
        author: "David Allen"
    },
    {
        text: "Lack of direction, not lack of time, is the problem. We all have twenty-four hour days.",
        author: "Zig Ziglar"
    },
    {
        text: "The art of being wise is knowing what to overlook.",
        author: "William James"
    },
    {
        text: "What you stay focused on will grow.",
        author: "Roy T. Bennett"
    }
];

// Get URL parameters
const params = new URLSearchParams(window.location.search);
const blockedUrl = params.get('url');
const blockedSite = params.get('site');

// Display blocked site
const siteElement = document.getElementById('blocked-site');
if (blockedSite) {
    siteElement.textContent = blockedSite;
} else if (blockedUrl) {
    try {
        const url = new URL(blockedUrl);
        siteElement.textContent = url.hostname;
    } catch (e) {
        siteElement.textContent = blockedUrl;
    }
} else {
    siteElement.textContent = 'Unknown site';
}

// Display random quote
const quote = quotes[Math.floor(Math.random() * quotes.length)];
document.getElementById('quote-text').textContent = `"${quote.text}"`;
document.getElementById('quote-author').textContent = `— ${quote.author}`;

// Prevent navigation back to blocked site
window.history.pushState(null, null, window.location.href);
window.addEventListener('popstate', () => {
    window.history.pushState(null, null, window.location.href);
});

// Update timer with time spent on this page
let secondsOnPage = 0;
const timerElement = document.getElementById('timer');

function updateTimer() {
    secondsOnPage++;
    const minutes = Math.floor(secondsOnPage / 60);
    const seconds = secondsOnPage % 60;

    if (minutes > 0) {
        timerElement.textContent = `Time on this page: ${minutes}m ${seconds}s`;
    } else {
        timerElement.textContent = `Time on this page: ${seconds}s`;
    }
}

setInterval(updateTimer, 1000);

// Log block to console for debugging
console.log('Website Blocker: Site blocked -', blockedSite || blockedUrl);
