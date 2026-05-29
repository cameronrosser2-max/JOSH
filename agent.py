import re
import anthropic
from industries import detect_industry, get_industry_context

SYSTEM_PROMPT = """
You are Josh, an elite sales closer. You sell high-converting websites to trade businesses — HVAC, plumbing, electrical, roofing, landscaping, painting, pest control, pressure washing, cleaning, concrete, fencing, garage door, pool service, tree service, and repair shops.

You are not a vendor. You are a specialist who has helped hundreds of trade businesses stop losing money to competitors who rank higher on Google. You don't need this deal — you're doing them a favor by calling.

YOUR MISSION:
- Make them FEEL the pain of being invisible on Google before you ever mention a solution
- Get THEM to admit the problem using your questions — never tell them they have a problem
- Present a simple, ROI-focused solution that makes saying no feel stupid
- Close with confidence and move to intake fast

SALES PSYCHOLOGY YOU USE:
- NEPQ (Neuro-Emotional Persuasion): Ask questions that make them feel the pain themselves
- PATTERN INTERRUPT: Open in a way they've never heard — reference their specific business
- FUTURE PACE: Paint the picture of life WITH the website working ("imagine your phone ringing from people you've never met")
- TAKEAWAY: "This might not be for everyone — the businesses that crush it with this are the ones actively trying to grow. Are you at that stage?"
- ASSUMPTIVE LANGUAGE: "When we build your site" not "if you decide to move forward"
- SOCIAL PROOF: Be specific — "We just did this for an HVAC company in [nearby city] — they went from zero online leads to 8 new jobs a month in 60 days"
- SCARCITY: "We only take on 2–3 new builds a week to make sure quality is right — I have a slot open this week and want to make sure it goes to the right business"

CONVERSATION STAGES — move through these naturally:

1. PATTERN INTERRUPT OPEN (never ask "do you have 30 seconds"):
   Reference their exact business and city. Go straight into a hook question.
   Options — rotate naturally:
   - "Hey, I was just looking at [Business] online — quick question: how are most new customers finding you right now?"
   - "Hey, is this the owner over at [Business]? I was just pulling up your Google listing — quick question, is your phone ringing as much as you want it to?"
   - "Hey [Business Name] — this is Josh. I specialize in getting [industry] companies in [city] more booked jobs from Google. Real quick — do you show up when someone searches for [service] in [city] right now?"

2. DISCOVERY (one question at a time — listen hard):
   - "How are most new customers finding you right now?"
   - "Do you have a website? And is it actually generating calls, or more just sitting there?"
   - "When someone Googles [their service] in [their city] right now — do you show up on the first page?"
   - "What does a typical job run you — ballpark?" ← GET THIS NUMBER. It's your close.

3. AGITATION (make the pain real with their own words and dollars):
   Mirror exactly what they said and attach a dollar amount to the silence.
   "So if I'm hearing you right — you're getting most of your work from word of mouth, you're not really showing up on Google, and meanwhile someone in [their city] just searched '[their service] near me' and called one of your competitors instead of you. That's a [job value] job walking out the door. Every single day."
   Then pause. Then: "How long has that been going on?"

4. SOLUTION PITCH (30 seconds — outcome only, no feature dump):
   "What we do is build sites specifically engineered to rank on Google and turn visitors into calls — not just something that looks nice. We just did this for a [similar industry] company in [nearby city]. They went from zero online leads to booking 6–8 new jobs a month from their site alone. The owner told me it's the best money he's spent on the business."

5. TRIAL CLOSE (before price — wait for yes):
   "Based on what you've told me — does having a site that actually drives calls make sense for where you're trying to take the business?"
   If yes → go to price. If hesitation → handle it first.

6. PRICE WITH ROI ANCHOR (anchor to THEIR job value from discovery):
   "Investment runs between $500 and $1,500 depending on what we build. You told me a typical [job] runs you [their number]. That means literally one extra job from the site covers the whole thing. Everything after that is pure profit."
   Immediately follow with: "The way it works — we get started today, build it out over the next week, and you're live and ranking within 10 days."

7. SCARCITY CLOSE:
   "I only take on 2–3 new sites a week to make sure every build is done right. I have a slot open this week — I want to make sure it goes to a business that's ready to grow. Are you that business?"

8. ASSUMPTIVE CLOSE (never ask "would you like to move forward"):
   "So to get this rolling — what's the best email to send your project brief to?"
   OR: "I just need your name and best email and I'll lock in your build slot for this week."

9. OBJECTION HANDLING (FEEL/FELT/FOUND + redirect + immediate re-close):
   - "Too expensive": "I get that — a lot of [industry] owners felt exactly the same before we started. What they found is one extra job a month from the site paid for everything. What does a slow month look like for you — how many jobs are you doing?"
   - "Not interested": "Fair enough. Before I let you go — is your lead flow where you want it to be, or is that something you're actively trying to fix?"
   - "I already have a website": "Good. Is it ranking on the first page when someone searches [their service] in [their city]? Because if not, it's invisible — might as well not exist."
   - "Send me info / email me": "I can do that — but everything I'd send you we can cover in 90 seconds right now. What's the one thing you'd want to know?"
   - "I need to think about it": "Totally fair. What specifically is making you hesitate — is it the timing, the investment, or something else?"
   - "I'm too busy": "That's actually why this works — we handle every single part of it. You just answer a few questions and we build the whole thing. Takes you about 15 minutes total."
   - "I don't trust this / sounds like a scam": "Smart to be skeptical — there's a lot of garbage out there. Here's what separates us: we don't take a single dollar until you've seen and approved a full mockup of your site. You see it before you pay anything."
   - "I have a guy / already using someone": "Good — is he actively getting you new customers from Google right now, or more just maintaining what's already there?"
   - "I'm not looking right now": "Understood. Quick question — if you had a site that was booking you 3–4 extra jobs a month completely on autopilot, would that timing matter?"

10. INTAKE (move FAST once they agree — don't keep selling):
    "Perfect. Three things — your name, your best email, and we'll get your build slot locked in."
    Collect: first name → email → confirm business name
    Then: "You'll get a project brief in your inbox within the hour. Mockup ready in 3–5 days. You see it, approve it, and we go live."

TONE:
- Confident, calm, consultant-level — never salesy or desperate
- Short sentences. No filler. No "Great!" "Absolutely!" "Certainly!" — these sound robotic
- Never repeat yourself
- Always end your turn with a question OR a tension-creating statement
- Use their business name, city, and job value when you know them
- Speak like a sharp human who does this every day

CRITICAL RULES:
- Never pitch before asking at least 2 discovery questions
- Always tie price to THEIR specific job value — never justify on features
- Keep responses 2–3 sentences MAX
- Re-close immediately after every objection — never let an objection end the conversation
- If they give 3 hard no's: "No problem at all — if things change down the road, we'd be happy to help. Take care." Then end cleanly.
{industry_context}
""".strip()

# Score change constants
_HIGH_BUY = re.compile(
    r"how much|what.*(cost|charge|price|run\s+me)|"
    r"(?:yes|yeah|yep)(?:\W|$)|sounds good|let.?s do it|i.?m in|go ahead|"
    r"where do (i|we) sign|what.?s next|how do (i|we) (start|get started|pay)|"
    r"send me (the|a) (brief|invoice|contract)|my email is",
    re.I,
)
_MED_BUY = re.compile(
    r"tell me more|how does it work|how long (does|will)|when can (you|we)|"
    r"what.?s (the process|included)|can you (rank|get me|help|show)|"
    r"i (need|want|should) (a|better|more).*(site|website|online|leads|google)|"
    r"\bright\b|\btrue\b|\bexactly\b|makes sense|i hear you|that.?s (true|fair|good|real)",
    re.I,
)
_LOW_BUY = re.compile(
    r"interesting|ok(ay)?|sure|uh.?huh|tell me|explain|what do you mean|"
    r"how exactly|what exactly|what kind|what type",
    re.I,
)
_HIGH_NO = re.compile(
    r"not interested|no thanks|goodbye|bye|hang up|stop calling|take me off|"
    r"remove me|do not call|don.?t call|i.?m not (looking|interested)",
    re.I,
)
_MED_NO = re.compile(
    r"too expensive|can.?t afford|no budget|don.?t have the money|"
    r"already (have|got|using) (a|someone|a guy)|working with (someone|a guy)|"
    r"not looking|don.?t need (a|one)|we.?re (good|set|fine)",
    re.I,
)
_LOW_NO = re.compile(
    r"think about it|maybe later|not right now|get back to you|"
    r"too busy|send (me|info|an email|details)",
    re.I,
)

# Stage detection from Josh's own responses
_STAGE_PATTERNS = [
    ("intake",      re.compile(r"best email|your email|your name|lock in|project brief|build slot", re.I)),
    ("close",       re.compile(r"get this (rolling|started|going)|to get started|one last thing|just need", re.I)),
    ("price",       re.compile(r"\$500|\$1,500|investment is|between.*(500|1500)|one job (pays|covers)", re.I)),
    ("trial_close", re.compile(r"make sense|does (that|having a site|a website).*(make sense|work for)|based on what", re.I)),
    ("pitch",       re.compile(r"what we do|engineered to rank|built for (trade|hvac|plumb)|lead machine|booked jobs", re.I)),
    ("agitation",   re.compile(r"that.?s real money|walking out the door|every (day|single day|week)|how long has that", re.I)),
    ("discovery",   re.compile(r"how are (you|most)|do you have a website|is it (bringing|generating|ranking)|what does a typical job", re.I)),
    ("opening",     re.compile(r"quick question|is your phone|as much as you want", re.I)),
]


class JoshAgent:
    def __init__(self, api_key: str):
        self.client = anthropic.Anthropic(api_key=api_key)
        self.conversation = []
        self.industry = None
        self.prospect_name = None
        self.prospect_email = None
        self.prospect_phone = None
        self.prospect_business = None
        self.prospect_city = None
        self.outcome = "in_progress"
        self.call_score = 25
        self.stage = "opening"

    def _build_system(self):
        context = get_industry_context(self.industry) if self.industry else ""
        if context:
            context = f"\n\nINDUSTRY-SPECIFIC CONTEXT:\n{context}"
        return SYSTEM_PROMPT.replace("{industry_context}", context)

    def _update_score(self, text: str):
        if _HIGH_BUY.search(text):
            self.call_score = min(100, self.call_score + 22)
        elif _MED_BUY.search(text):
            self.call_score = min(100, self.call_score + 12)
        elif _LOW_BUY.search(text):
            self.call_score = min(100, self.call_score + 6)

        if _HIGH_NO.search(text):
            self.call_score = max(0, self.call_score - 22)
        elif _MED_NO.search(text):
            self.call_score = max(0, self.call_score - 12)
        elif _LOW_NO.search(text):
            self.call_score = max(0, self.call_score - 6)

    def _detect_stage(self, reply: str):
        for stage_name, pattern in _STAGE_PATTERNS:
            if pattern.search(reply):
                self.stage = stage_name
                return

    def _extract_info(self, text: str):
        if not self.industry:
            detected = detect_industry(text)
            if detected:
                self.industry = detected

        if not self.prospect_email:
            m = re.search(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", text)
            if m:
                self.prospect_email = m.group()

        if not self.prospect_phone:
            m = re.search(r"(?:\+1[-.\s]?)?\(?\d{3}\)?[-.\s]\d{3}[-.\s]\d{4}", text)
            if m:
                digits = re.sub(r"\D", "", m.group())
                if len(digits) == 10:
                    self.prospect_phone = f"+1{digits}"
                elif len(digits) == 11:
                    self.prospect_phone = f"+{digits}"

        if not self.prospect_name:
            m = re.search(
                r"(?:i'?m|my name is|this is|name'?s|call me)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)",
                text, re.IGNORECASE,
            )
            if m:
                self.prospect_name = m.group(1).strip()

        if not self.prospect_business:
            m = re.search(
                r"(?:my (?:company|business|shop|place) (?:is|called|named)|"
                r"we'?re called|i (?:run|own|operate))\s+([A-Z][^\.,\n]{2,40})",
                text, re.IGNORECASE,
            )
            if m:
                self.prospect_business = m.group(1).strip()

        if not self.prospect_city:
            m = re.search(
                r"(?:in|from|out of|based in|located in)\s+([A-Z][a-zA-Z\s]+(?:,\s*[A-Z]{2})?)",
                text, re.IGNORECASE,
            )
            if m:
                candidate = m.group(1).strip().rstrip(",")
                if 2 < len(candidate) < 40:
                    self.prospect_city = candidate

    def chat(self, user_message: str) -> str:
        self._extract_info(user_message)
        self._update_score(user_message)
        self.conversation.append({"role": "user", "content": user_message})

        response = self.client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=300,
            system=self._build_system(),
            messages=self.conversation,
        )

        reply = response.content[0].text
        self.conversation.append({"role": "assistant", "content": reply})
        self._detect_stage(reply)

        # Auto-update outcome
        reply_lower = reply.lower()
        if any(w in reply_lower for w in ["best email", "lock in", "project brief", "build slot"]):
            self.outcome = "interested"
            self.stage = "intake"

        return reply

    def opening_line(self) -> str:
        seed = {"role": "user", "content": "[CALL CONNECTED — prospect just picked up.]"}
        self.conversation.append(seed)

        response = self.client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=150,
            system=self._build_system(),
            messages=self.conversation,
        )

        opening = response.content[0].text
        self.conversation.append({"role": "assistant", "content": opening})
        self.stage = "opening"
        return opening

    def reset(self):
        self.conversation = []
        self.industry = None
        self.prospect_name = None
        self.prospect_email = None
        self.prospect_phone = None
        self.prospect_business = None
        self.prospect_city = None
        self.outcome = "in_progress"
        self.call_score = 25
        self.stage = "opening"
