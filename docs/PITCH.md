# Aangan: the pitch

*Aangan (आँगन): the courtyard where an Indian family gathers. Now it has a voice.*

## The 10-second version

Every family has one person who remembers everything: who is allergic to what, whose bill is due, what Dadi eats, who is collecting the prescription. When they are busy, it falls apart. **Aangan is that person, as an assistant everyone can just talk to** in their own language and their own voice.

## Why it is needed

1. **Family logistics is invisible work.** It lives in one person's head and in a dozen WhatsApp threads. Nothing is shared, nothing is assigned, and everything is a reminder away from being forgotten.
2. **The people who need help most cannot use apps.** A grandparent will not open a travel site, a shopping list or a calendar. They will talk. Voice is the only interface that includes all four generations in one home.
3. **Today's assistants are built for one person.** Alexa and Google Assistant answer an individual. A family is a group with shared memory, conflicting preferences, shared money and shared plans. Nobody plans a trip, a week or a shopping list alone.
4. **India is not English-only.** Hindi, Telugu, Kannada and Hinglish are how families really talk, and a voice that sounds like a stranger is a voice nobody trusts.

## What Aangan is

One shared family memory and a team of specialist agents that act for it:

| Agent | What it does for the family |
|---|---|
| Family Room | The family talks together (typing, voice or video) and the trip plan builds itself on screen: live flights, train, bus and car options, a stay, meals, and a running cost against the budget |
| Tasks and shopping | "Remind Rahul to pay the bill tomorrow" creates a task, assigns it and notifies him. "We need milk" lands on the shared list |
| Calendar | Checks everyone's day before suggesting anything |
| Dining | Books a table that respects every allergy and diet at it |
| School and senior care | Tells parents about school, and notices when Dadi has not checked in |
| Household memory | Remembers allergies, diets, access needs, budgets, routines |
| Smart home | "Turn off the kitchen lights" in a 3D virtual house |

It acts on its own memory: **adding peanut chutney to the list warns you that Aarav is allergic.** That is the difference between a chatbot and a family member.

## The demo (3 minutes)

1. **A family plans a trip by talking.** Two people speak in the Family Room. The plan builds itself on screen with live flights and train, bus and car estimates, and the cost bar tracks the budget. Change the destination or dates out loud and everything re-fits.
2. **It never books behind your back.** Aangan proposes, the host approves.
3. **Plan my day.** Rahul asks. Aangan reads his calendar, what he owes (the overdue bill first), the shopping he is on, and what the family remembers about him.
4. **Assign by voice.** "Ask Priya to book the plumber." Priya is notified.
5. **The safety catch.** Add something Aarav is allergic to. Aangan warns before it is bought.
6. **Open to the world.** Show another agent using the same household through MCP.

## Why it wins on each judge's ground

- **Agora:** voice is the product, not a feature. Real-time voice and video rooms with several people, a per-member voice agent, and our backend as the agent's brain behind Agora's LLM endpoint.
- **Murf:** a distinct Falcon voice for every family member (Pooja, Rachna, Nikhil, Abhinav), speaking in the language they spoke. Voice identity is what makes it feel like a person in the house.
- **MakeMyTrip:** group travel is where families struggle most. One room gathers everyone's budget, dates and preferences and compares flights, trains, buses and driving in one view with the cost against budget. This is the gap between searching alone and deciding together.
- **Agentic workflow (PS21):** eight specialists, tool calling over shared state, a fast rule path for clear requests and a model path for open ones. It explains what it did, asks before it books, and falls back safely.

## Why it is built to last

- **Fast and cheap:** clear requests are answered by the rule engine in milliseconds, with no model call. Only open-ended ones reach an LLM.
- **Resilient:** Cloudflare AI Gateway first, Vercel AI Gateway as the backup, several models in the chain. If a provider rate limits, the family does not notice.
- **Honest by design:** the app labels samples and estimates. Bookings are demo bookings, and nothing moves money without approval.
- **Open:** every tool is also an MCP server, so other agents plug into the family's shared memory instead of rebuilding it.

## What is real and what is next

**Real today:** Agora voice sessions and rooms, Murf voices, the tool-calling brain, all agents' logic, live flight search, the shared household, and the PWA.
**Next:** real providers behind each catalogue (MakeMyTrip for flights, hotels and buses, a restaurant and pharmacy partner), each swapped in behind the same tool without touching the rest; per-person accounts; and wider language coverage with real microphones.

## The close

> Big tech built assistants for one person at a time. Families do not live that way. They plan together, forget together and look after each other. **Aangan is the first assistant that belongs to the whole family.** It remembers what matters, speaks everyone's language, and takes the invisible work off the one person who has been carrying it.

## Likely questions

- **"Is this just a chatbot?"** No. It has shared memory, assigns work to people, notifies them, and refuses or warns when something clashes with what it knows.
- **"What if the model is wrong?"** It never books alone, and clear requests do not go through a model at all.
- **"What stops it going down?"** Two gateways and a model chain, with the rule engine answering the common cases on its own.
- **"Is the data real?"** Voice, the agents' logic and live flights are real. Hotels, places and restaurants are labelled samples, and fares for trains, buses and cars are labelled estimates.
- **"What is the business?"** The family subscription, and booking referrals through travel, dining and pharmacy partners that plug in behind the same tools.
