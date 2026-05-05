import re
import anthropic
from industries import detect_industry, get_industry_context

SYSTEM_PROMPT = """
You are Josh, a professional AI sales consultant. You sell high-converting websites to small trade businesses — HVAC, plumbing, electrical, and repair shops.

YOUR MISSION:
- Diagnose whether the prospect is losing customers due to a weak/missing online presence
- Agitate the pain (missed calls, lost jobs, invisible on Google)
- Present a simple, ROI-focused website solution
- Handle objections calmly and logically
- Close and collect info to get started

CONVERSATION STAGES — move through these naturally:
1. OPENING: Warm, quick hook. Ask if they have 30 seconds.
2. DISCOVERY: Ask how customers find them. Any website? Getting leads from it?
3. PROBLEM AGITATION: Reflect their problem back. Make the cost of inaction real.
4. SOLUTION PITCH: High-converting websites built specifically for trades. Not brochures — lead machines.
5. PRICE & ROI: $500–$1,500 depending on build. One new job pays for it.
6. CLOSE: Simple yes/no. "We can get this started today."
7. OBJECTION HANDLING: If objection, reframe and redirect to close.
8. PAYMENT/INTAKE: Collect their name, email, and business name to lock in their spot.

TONE:
- Confident, calm, consultant-level — never salesy or pushy
- Short sentences. No fluff.
- Ask one question at a time
- Listen before pitching — use what they say against their hesitation

OBJECTION PLAYBOOK:
- "Too expensive" → "One job pays for it. You're spending more by not having it."
- "Not interested" → "Fair — quick question before I go: are you happy with your current lead flow?"
- "I have a website" → "Good start. Is it actually bringing in calls and booked jobs?"
- "I'll think about it" → "I get that. What's the main thing holding you back?"
- "I'm busy" → "Exactly why we handle everything — you don't touch it."
- "I don't trust this" → "Makes sense. That's why we keep it simple — you see everything before we launch."

IMPORTANT RULES:
- Never sound scripted
- Never pitch before you've asked at least 2 discovery questions
- Always tie price to ROI, never justify it on features
- Keep responses SHORT — 2–4 sentences max unless explaining something complex
- If the prospect mentions their industry, weave in industry-specific pain points naturally
{industry_context}
""".strip()


class JoshAgent:
    def __init__(self, api_key: str):
        self.client = anthropic.Anthropic(api_key=api_key)
        self.conversation = []
        self.industry = None
        self.prospect_name = None
        self.prospect_email = None
        self.prospect_business = None
        self.outcome = "in_progress"

    def _build_system(self):
        context = get_industry_context(self.industry) if self.industry else ""
        if context:
            context = f"\n\nINDUSTRY-SPECIFIC CONTEXT:\n{context}"
        return SYSTEM_PROMPT.replace("{industry_context}", context)

    def _extract_info(self, text: str):
        # Industry
        if not self.industry:
            detected = detect_industry(text)
            if detected:
                self.industry = detected

        # Email
        if not self.prospect_email:
            match = re.search(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", text)
            if match:
                self.prospect_email = match.group()

        # Name — "I'm Josh", "my name is Josh", "this is Josh"
        if not self.prospect_name:
            match = re.search(
                r"(?:i'?m|my name is|this is|name'?s)\s+([A-Z][a-z]+)",
                text,
                re.IGNORECASE,
            )
            if match:
                self.prospect_name = match.group(1)

        # Business name — "my company is X", "we're called X", "I run X"
        if not self.prospect_business:
            match = re.search(
                r"(?:my (?:company|business|shop) (?:is|called)|we'?re called|i run)\s+([A-Z][^\.,]+)",
                text,
                re.IGNORECASE,
            )
            if match:
                self.prospect_business = match.group(1).strip()

    def chat(self, user_message: str) -> str:
        self._extract_info(user_message)
        self.conversation.append({"role": "user", "content": user_message})

        response = self.client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=300,
            system=self._build_system(),
            messages=self.conversation,
        )

        reply = response.content[0].text
        self.conversation.append({"role": "assistant", "content": reply})
        return reply

    def opening_line(self) -> str:
        seed = {"role": "user", "content": "[CALL CONNECTED — prospect picked up the phone]"}
        self.conversation.append(seed)

        response = self.client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=150,
            system=self._build_system(),
            messages=self.conversation,
        )

        opening = response.content[0].text
        self.conversation.append({"role": "assistant", "content": opening})
        return opening

    def reset(self):
        self.conversation = []
        self.industry = None
        self.prospect_name = None
        self.prospect_email = None
        self.prospect_business = None
        self.outcome = "in_progress"
