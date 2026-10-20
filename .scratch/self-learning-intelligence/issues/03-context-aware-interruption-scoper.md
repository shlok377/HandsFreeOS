# 03: [Intelligence] Context-aware interruption and abort scoper

**What to build:** Refactors the live interruption gate so speech containing action verbs like "Quit Discord from my browser" or farewells like "Bye bye" or "Quit, quit" are not prematurely intercepted as emergency aborts. Live interruption is scoped strictly to: (1) halting in-flight physical actions (active mouse trajectory or continuous keyboard typing) in <25ms, or (2) explicit, standalone emergency halt words (e.g. "Wait!", "Stop!", "Cancel!"). Action-oriented sentences proceed to intent routing.

**Blocked by:** None (can start immediately)

**Status:** ready-for-agent

- [ ] Interruption coordinator differentiates between standalone abort signals ("Wait", "Stop", "Abort") and verb-object commands ("Quit Discord", "Stop the music").
- [ ] Emergency hardware abort is triggered only if an input action is actively executing or an unambiguous emergency halt keyword is spoken.
- [ ] Utterances with intent payloads pass through to the semantic reasoner without returning premature `ActionType.ABORT`.
- [ ] Unit tests verify that "Quit Discord" proceeds to intent handling while "Wait" and "Stop" trigger immediate abort.
