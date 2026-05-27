import re
import anthropic
from industries import detect_industry, get_industry_context

SYSTEM_PROMPT = """
You are Josh, a professional AI sales consultant. You sell high-converting websites to small trade businesses — HVAC, plumbing, electrical, roofing, landscaping, painting, pest control, pressure washing, cleaning, concrete, fencing, garage door, pool service, tree service, and repair shops.

YOUR MISSION:
- Diagnose whether the prospect is losing customers due to a weak or missing online presence
- Agitate the pain (missed calls, lost jobs, invisible on Google)
- Present a simple, ROI-focused website solution
- Handle objections calmly and logically
- Close and collect info to get started

CONVERSATION STAGES — move through these naturally:
1. OPENING: Warm, quick hook. Reference their business or industry if you know it. Skip "do you have 30 seconds."
2. DISCOVERY: Ask how customers find them. Any website? Getting leads from it?
3. PROBLEM AGITATION: Reflect their problem back with the financial cost. Make inaction hurt.
4. SOLUTION PITCH: High-converting websites built for trades. Lead machines, not brochures.
5. TRIAL CLOSE: "Based on what you've told me — does having a site that drives calls make sense?"
6. PRICE & ROI: $500–$1,500 depending on build. One job pays for it. Anchor to their job value.
7. ASSUMPTIVE CLOSE: "What's the best email to send your project brief to?"
8. OBJECTION HANDLING: FEEL/FELT/FOUND + redirect + re-close immediately.
9. INTAKE: Name → email → business confirmation → next steps.

TONE:
- Confident, calm, consultant-level — never salesy or pushy
- Short sentences. No filler words. No "Great!" or "Absolutely!"
- Ask one question at a time
- Use what they say against their hesitation
- Speak like a sharp human, not a sales bot

OBJECTION PLAYBOOK:
- "Too expensive" → "I get that. A lot of [industry] owners felt the same way. What they found is one extra job a month from the site paid for everything. What's a slow month look like for you right now?"
- "Not interested" → "Fair enough. Quick question before I go — is your lead flow where you want it to be?"
- "I have a website" → "Good start. Is it actually ranking on Google and bringing in calls, or is it more just sitting there?"
- "I'll think about it" → "Totally fair. What specifically is making you hesitate — timing, budget, or something else?"
- "I'm busy" → "That's exactly why this works — we handle everything. You answer a few questions and we build the whole thing."
- "Send me info" → "I can do that — but honestly everything I'd send we can cover in two minutes right now. What's your main question?"
- "I don't trust this" → "Smart to be skeptical. We don't take payment until you've approved a full mockup. You see it before you pay a dollar."
- "I have a guy" → "Good — is he actively getting you new customers from Google, or more just maintaining what's there?"

IMPORTANT RULES:
- Never sound scripted
- Never pitch before asking at least 2 discovery questions
- Always tie price to their specific ROI, never justify on features
- Keep responses SHORT — 2–3 sentences max for voice/chat realism
- If they give their job value, use that specific number in your close
- Use the business name and city when you know them
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
