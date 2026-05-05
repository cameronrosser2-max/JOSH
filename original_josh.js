// AI Cold Calling Agent - "Josh"
// Designed for Claude / LLM API usage

const systemPrompt = `
You are Josh, a professional AI sales consultant specializing in selling high-converting websites to small businesses.

Your objective:
- Diagnose business problems
- Identify revenue leaks
- Present a simple website solution
- Handle objections
- Close the sale and collect payment on the call

Tone:
- Confident, calm, professional
- Direct and efficient
- Never pushy or desperate
- Speak like a consultant

Rules:
- Always control the conversation
- Ask questions before pitching
- Focus on ROI, not features
- Redirect objections into logical buying reasons
- Never sound scripted
`;


// Conversation State Machine
const STATES = {
  OPENING: "opening",
  DISCOVERY: "discovery",
  PROBLEM_AGITATION: "problem_agitation",
  SOLUTION_PITCH: "solution_pitch",
  PRICE_ANCHOR: "price_anchor",
  CLOSE: "close",
  OBJECTION: "objection",
  PAYMENT: "payment",
  EXIT: "exit"
};


// Objection Handler
function handleObjection(input) {
  const lower = input.toLowerCase();

  if (lower.includes("expensive") || lower.includes("price")) {
    return "I understand — but the real issue is how many customers you're losing right now. If this brings even 2 extra jobs, it pays for itself.";
  }

  if (lower.includes("trust") || lower.includes("legit") || lower.includes("scam")) {
    return "That's fair — most businesses felt that way initially. That's why we keep everything simple, transparent, and focused on actual results.";
  }

  if (lower.includes("busy") || lower.includes("time")) {
    return "Exactly — that's why we handle everything for you. This doesn't take your time, it saves it.";
  }

  if (lower.includes("not interested")) {
    return "Totally understand — quick question before I go: if your website could consistently bring in more customers, would that matter to you?";
  }

  return "I hear you — but based on what you told me, this is something that would directly improve your customer flow.";
}


// Main Response Generator
function generateResponse(state, userInput) {
  switch (state) {

    case STATES.OPENING:
      return {
        nextState: STATES.DISCOVERY,
        response: "Hey, this is Josh — quick question. I was looking at your business online and noticed something that might be costing you customers. Mind if I take 30 seconds?"
      };

    case STATES.DISCOVERY:
      return {
        nextState: STATES.PROBLEM_AGITATION,
        response: "How are most of your customers finding you right now? And are you getting consistent leads from your website?"
      };

    case STATES.PROBLEM_AGITATION:
      return {
        nextState: STATES.SOLUTION_PITCH,
        response: "Got it — so right now, you're likely missing out on customers because your site isn't converting visitors into actual paying clients."
      };

    case STATES.SOLUTION_PITCH:
      return {
        nextState: STATES.PRICE_ANCHOR,
        response: "What we do is build high-converting websites designed specifically to turn visitors into calls and booked jobs — not just something that looks good."
      };

    case STATES.PRICE_ANCHOR:
      return {
        nextState: STATES.CLOSE,
        response: "Most businesses make back the cost from just 1–2 new customers. We typically charge $500–$1500 depending on the build, but based on what you said, we can get this started immediately."
      };

    case STATES.CLOSE:
      return {
        nextState: STATES.PAYMENT,
        response: "Instead of dragging this into meetings, we can just get this handled today and start improving your lead flow. I can set you up right now — takes 2 minutes."
      };

    case STATES.OBJECTION:
      return {
        nextState: STATES.CLOSE,
        response: handleObjection(userInput)
      };

    case STATES.PAYMENT:
      return {
        nextState: STATES.EXIT,
        response: "Perfect — I'll get this started. I just need your name, email, and we'll lock in your spot to begin."
      };

    case STATES.EXIT:
      return {
        nextState: null,
        response: "Appreciate your time — looking forward to getting results for you."
      };

    default:
      return {
        nextState: STATES.OBJECTION,
        response: handleObjection(userInput)
      };
  }
}


// Example Runner
function runAgent(userInputs) {
  let state = STATES.OPENING;

  userInputs.forEach(input => {
    const { nextState, response } = generateResponse(state, input);
    console.log("AI:", response);
    state = nextState || state;
  });
}


// Example Simulation
runAgent([
  "Yeah sure",
  "Mostly from Google",
  "Not really getting leads",
  "Sounds expensive",
  "Okay maybe"
]);
