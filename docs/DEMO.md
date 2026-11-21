# Demo script: Aangan (3 minutes)

**One line:** a family voice assistant where specialist agents *act* (book, check calendars, rebook, tell the right people), and a Family Room where everyone talks a trip into a plan that builds itself on screen.

| Judge | What they should see |
|---|---|
| Agora | Conversational AI Engine in the loop: ASR, our own tool-calling LLM endpoint, TTS; the RTC room with several people and the agent; our endpoint streams, speaks a lead-in while tools run. |
| Murf | Falcon voices, one per family member, in Indian locales (en-IN, hi-IN; Telugu and Kannada through the multi-native voices). |
| MakeMyTrip | Trip planning end to end: live flights, train, bus and car alternatives, a stay, a day by day plan with costs against a budget, and a host approval before anything is booked. |

## Before you go on (30 minutes ahead)

1. The hosted URL opens and `/api/config` shows `voice`, `murf` and `llm` as configured.
2. Open it on the phone you will demo on, install it (Settings, Install), allow the microphone.
3. Settings, Reset, then load the demo family. Language: English.
4. Start a Family Room from Home ("Plan together") and keep its link ready. A second device or a second browser joins as a guest.
5. Do one full voice turn to warm everything (the free host sleeps after 15 idle minutes and takes about a minute to wake).
6. Have the recorded backup video open in another tab.

## The 3 minutes

**0:00 The problem (15 s).** "Families run on five calendars, three apps and one tired person who remembers everything. Aangan is that person, as a team of agents."

**0:15 Instant answers (30 s).** Tap the mic. Say: *"When is everyone free on Sunday?"*
It answers from the real calendars in well under a second (the rule engine takes the clear questions; the LLM takes the open ones). Point out: it names who is holding the slot (Aarav's swimming, Rahul's call, Dadi's satsang).

**0:45 It acts (45 s).** Say: *"Book a cab for Dadi on Sunday morning."*
Aangan checks Dadi's satsang and the calendar, books through its travel tool, and the family gets notified. Open Settings and run **Rahul's flight delayed**: the agents notice, rebook, move the cab and tell the family without being asked. Then switch on **Simulate a supplier failure** and run it again to show it recovering. This is the agentic workflow: trigger, decide, act, notify.
Then the everyday part: say *"We need curd and chicken"* (it goes on the shared list and warns that Dadi is vegetarian), *"Ask Rahul to do the groceries"* (he gets the list as an errand and a notification), *"Remind Rahul to pay the water bill tomorrow"* (an assigned task), and finally *"Plan my day"* as Rahul: overdue first, then today, then the shopping he owes. Family tab, Tasks shows all of it.

**1:30 The Family Room (75 s).** Open the room. Two people are in it (second device joins as a guest). Tap **Talk to Aangan** and say:
*"Plan a family trip from Bengaluru to Goa, 26 to 28 December, four of us, budget forty thousand. We prefer the train, and public transport once there."*
Watch the left side build: dates, travellers, Dadi's step-free needs and Aarav's peanut allergy pulled from the household memory, places and meals for each day, the cost against the budget on the board and the map.
Then say: *"Actually let's fly instead."* The flights appear with live prices and replace the train, and the total changes. At this budget the flights push the plan over it: Aangan says so plainly and offers a way to bring it down (a nice moment, leave it in). Say: *"Book the nonstop flight."* Aangan does **not** book: it asks the host to approve, the host taps Approve, and a demo booking is made.

**2:45 Close (15 s).** "Voice from Agora, voices from Murf, tools and agents ours. English, Hindi, Telugu and Kannada. Nothing books without a human saying yes."

## If something goes wrong

| Problem | Do this |
|---|---|
| Voice will not connect or hear you | Use **Ask Aangan** and type the same sentence. The plan builds the same way. |
| A reply is slow | Say "that is the model thinking" and carry on: clear questions use the instant path; the first spoken words come within 1 to 3 seconds. |
| Wifi is poor | Play the backup video. Do not debug live. |
| The room looks stale | Reload; it picks the server state up again by itself. |

## Questions to expect, with honest answers

- **Is the flight data real?** Flights come from a live search when it is available and are labelled *Live*; otherwise the board marks them *Sample*. Hotels, places and restaurants are sample data and say so. Train, bus and car options are estimates from distance and say so.
- **Does it really book?** No. It proposes, the host approves, and a clearly marked demo booking is created. No money moves.
- **Why your own LLM endpoint?** Agora lets the engine call any OpenAI-compatible endpoint, so tool calling, family memory and the planner stay ours.
- **How is latency handled?** Clear questions skip the model; open ones stream, and a short spoken lead-in covers the tool wait. Model rate limits fall through to the next model at once.
- **What is not finished?** Hindi, Telugu and Kannada speech recognition and per-turn voice switching are built but not verified with a microphone. Two people speaking at once is untested. Agora Chat delivery is not configured.

## Numbers you can quote

- 1,387 automated tests pass.
- First spoken word in about 1 to 3 seconds for planning turns; clear calendar questions under 50 ms.
- Agora Conversational AI: 300 free minutes, then $0.10 a minute. A 3-minute demo uses a few of them.
