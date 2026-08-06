# The tell catalogue

Twenty-nine tells of AI writing, each with the fix. Distilled from [Wikipedia:Signs of AI
writing](https://en.wikipedia.org/wiki/Wikipedia:Signs_of_AI_writing), maintained by
WikiProject AI Cleanup, whose patterns come from thousands of observed instances.

Check a draft against every one. The worked example at the end runs all of them at once.

## Content tells

### 1. Inflated significance

Words to watch: stands/serves as, is a testament/reminder, a vital/significant/crucial/pivotal/key role/moment, underscores/highlights its importance, reflects broader, symbolizing its ongoing/enduring/lasting, contributing to the, setting the stage for, marking/shaping the, represents/marks a shift, key turning point, evolving landscape, focal point, indelible mark, deeply rooted

Puffs up importance by claiming an arbitrary detail represents some broader topic.

Before: The Statistical Institute of Catalonia was officially established in 1989, marking a pivotal moment in the evolution of regional statistics in Spain. This initiative was part of a broader movement across Spain to decentralize administrative functions and enhance regional governance.

After: The Statistical Institute of Catalonia was established in 1989 to collect and publish regional statistics independently from Spain's national statistics office.

### 2. Inflated notability

Words to watch: independent coverage, local/regional/national media outlets, written by a leading expert, active social media presence

Lists sources and follower counts instead of saying what was said.

Before: Her views have been cited in The New York Times, BBC, Financial Times, and The Hindu. She maintains an active social media presence with over 500,000 followers.

After: In a 2024 New York Times interview, she argued that AI regulation should focus on outcomes rather than methods.

### 3. Superficial "-ing" analyses

Words to watch: highlighting/underscoring/emphasizing..., ensuring..., reflecting/symbolizing..., contributing to..., cultivating/fostering..., encompassing..., showcasing...

A present participle phrase tacked onto a sentence to add depth it does not have.

Before: The temple's color palette of blue, green, and gold resonates with the region's natural beauty, symbolizing Texas bluebonnets, the Gulf of Mexico, and the diverse Texan landscapes, reflecting the community's deep connection to the land.

After: The temple uses blue, green, and gold. The architect said these were chosen to reference local bluebonnets and the Gulf coast.

### 4. Promotional language

Words to watch: boasts a, vibrant, rich (figurative), profound, enhancing its, showcasing, exemplifies, commitment to, natural beauty, nestled, in the heart of, groundbreaking (figurative), renowned, breathtaking, must-visit, stunning

Tourist-brochure tone, worst on anything that could be called cultural heritage.

Before: Nestled within the breathtaking region of Gonder in Ethiopia, Alamata Raya Kobo stands as a vibrant town with a rich cultural heritage and stunning natural beauty.

After: Alamata Raya Kobo is a town in the Gonder region of Ethiopia, known for its weekly market and 18th-century church.

### 5. Vague attribution

Words to watch: Industry reports, Observers have cited, Experts argue, Some critics argue, several sources/publications (when few are cited)

Opinions credited to an authority nobody can look up.

Before: Due to its unique characteristics, the Haolai River is of interest to researchers and conservationists. Experts believe it plays a crucial role in the regional ecosystem.

After: The Haolai River supports several endemic fish species, according to a 2019 survey by the Chinese Academy of Sciences.

### 6. "Challenges and future prospects" sections

Words to watch: Despite its... faces several challenges, Despite these challenges, Challenges and Legacy, Future Outlook

A formulaic section that concedes generic problems and then waves them away.

Before: Despite its industrial prosperity, Korattur faces challenges typical of urban areas, including traffic congestion and water scarcity. Despite these challenges, with its strategic location and ongoing initiatives, Korattur continues to thrive as an integral part of Chennai's growth.

After: Traffic congestion increased after 2015 when three new IT parks opened. The municipal corporation began a stormwater drainage project in 2022 to address recurring floods.

## Language and grammar tells

### 7. AI vocabulary

Words to watch: actually, additionally, align with, crucial, delve, emphasizing, enduring, enhance, fostering, garner, highlight (verb), interplay, intricate/intricacies, key (adjective), landscape (abstract), pivotal, showcase, tapestry (abstract), testament, underscore (verb), valuable, vibrant

These appear far more often in post-2023 text, and they cluster: find one, look for three more.

Before: Additionally, a distinctive feature of Somali cuisine is the incorporation of camel meat. An enduring testament to Italian colonial influence is the widespread adoption of pasta in the local culinary landscape, showcasing how these dishes have integrated into the traditional diet.

After: Somali cuisine also includes camel meat, which is considered a delicacy. Pasta dishes, introduced during Italian colonization, remain common, especially in the south.

### 8. Copula avoidance

Words to watch: serves as/stands as/marks/represents [a], boasts/features/offers [a]

An elaborate construction where "is" or "has" would do.

Before: Gallery 825 serves as LAAA's exhibition space for contemporary art. The gallery features four separate spaces and boasts over 3,000 square feet.

After: Gallery 825 is LAAA's exhibition space for contemporary art. The gallery has four rooms totaling 3,000 square feet.

### 9. Negative parallelism and tailing negation

"Not only... but...", "It's not just about..., it's...". Also the clipped fragment tacked onto a sentence end: "no guessing", "no wasted motion".

Before: It's not just about the beat riding under the vocals; it's part of the aggression and atmosphere. It's not merely a song, it's a statement.

After: The heavy beat adds to the aggressive tone.

Before: The options come from the selected item, no guessing.

After: The options come from the selected item without forcing the user to guess.

### 10. Rule of three

Ideas forced into groups of three to sound comprehensive.

Before: The event features keynote sessions, panel discussions, and networking opportunities. Attendees can expect innovation, inspiration, and industry insights.

After: The event includes talks and panels. There is also time for informal networking between sessions.

### 11. Elegant variation

Repetition penalties push the model to rename one thing every time it recurs.

Before: The protagonist faces many challenges. The main character must overcome obstacles. The central figure eventually triumphs. The hero returns home.

After: The protagonist faces many challenges but eventually triumphs and returns home.

### 12. False ranges

"From X to Y" where X and Y are not ends of any scale.

Before: Our journey through the universe has taken us from the singularity of the Big Bang to the grand cosmic web, from the birth and death of stars to the enigmatic dance of dark matter.

After: The book covers the Big Bang, star formation, and current theories about dark matter.

### 13. Hidden actors

Passive voice and subjectless fragments that drop whoever is doing the thing. Rewrite active where the actor is known.

Before: No configuration file needed. The results are preserved automatically.

After: You do not need a configuration file. The system preserves the results automatically.

## Style tells

### 14. Em dashes

Used far more than humans use them, in imitation of punchy sales writing. Most rewrite cleanly as commas, periods or parentheses.

Before: The term is primarily promoted by Dutch institutions—not by the people themselves. You don't say "Netherlands, Europe" as an address—yet this mislabeling continues—even in official documents.

After: The term is primarily promoted by Dutch institutions, not by the people themselves. You don't say "Netherlands, Europe" as an address, yet this mislabeling continues in official documents.

### 15. Mechanical boldface

Before: It blends **OKRs (Objectives and Key Results)**, **KPIs (Key Performance Indicators)**, and visual strategy tools such as the **Business Model Canvas (BMC)** and **Balanced Scorecard (BSC)**.

After: It blends OKRs, KPIs, and visual strategy tools like the Business Model Canvas and Balanced Scorecard.

### 16. Inline-header lists

List items that open with a bolded label and a colon, where prose would carry it.

Before:

> - **User Experience:** The user experience has been significantly improved with a new interface.
> - **Performance:** Performance has been enhanced through optimized algorithms.
> - **Security:** Security has been strengthened with end-to-end encryption.

After: The update improves the interface, speeds up load times through optimized algorithms, and adds end-to-end encryption.

### 17. Title case headings

Before: `## Strategic Negotiations And Global Partnerships`

After: `## Strategic negotiations and global partnerships`

### 18. Emojis

Before:

> 🚀 **Launch Phase:** The product launches in Q3
> 💡 **Key Insight:** Users prefer simplicity
> ✅ **Next Steps:** Schedule follow-up meeting

After: The product launches in Q3. User research showed a preference for simplicity. Next step: schedule a follow-up meeting.

### 19. Curly quotation marks

Before: He said “the project is on track” but others disagreed.

After: He said "the project is on track" but others disagreed.

## Chatbot tells

### 20. Correspondence artifacts

Words to watch: I hope this helps, Of course!, Certainly!, You're absolutely right!, Would you like..., let me know, here is a...

Chat wrapper pasted in along with the content.

Before: Here is an overview of the French Revolution. I hope this helps! Let me know if you'd like me to expand on any section.

After: The French Revolution began in 1789 when financial crisis and food shortages led to widespread unrest.

### 21. Knowledge-cutoff disclaimers

Words to watch: as of [date], Up to my last training update, While specific details are limited/scarce..., based on available information...

Before: While specific details about the company's founding are not extensively documented in readily available sources, it appears to have been established sometime in the 1990s.

After: The company was founded in 1994, according to its registration documents.

### 22. Sycophancy

Before: Great question! You're absolutely right that this is a complex topic. That's an excellent point about the economic factors.

After: The economic factors you mentioned are relevant here.

## Filler and hedging tells

### 23. Filler phrases

- "In order to achieve this goal" to "To achieve this"
- "Due to the fact that it was raining" to "Because it was raining"
- "At this point in time" to "Now"
- "In the event that you need help" to "If you need help"
- "The system has the ability to process" to "The system can process"
- "It is important to note that the data shows" to "The data shows"

### 24. Stacked hedges

Before: It could potentially possibly be argued that the policy might have some effect on outcomes.

After: The policy may affect outcomes.

### 25. Generic positive conclusions

Before: The future looks bright for the company. Exciting times lie ahead as they continue their journey toward excellence. This represents a major step in the right direction.

After: The company plans to open two more locations next year.

### 26. Corporate compound clichés

Words to watch: cross-functional, client-facing, data-driven, decision-making, best-in-class, high-quality, end-to-end, real-time, value-add, mission-critical

The tell is the consulting vocabulary, not the hyphen, so replace the phrase rather than unhyphenating it.

Before: The cross-functional team delivered a high-quality, data-driven report on our client-facing tools. Their decision-making process was well-known for being thorough.

After: The team pulled people from design, support and engineering. They read the numbers before they wrote the report, and they took their time over it.

### 27. Persuasive authority tropes

Phrases to watch: the real question is, at its core, in reality, what really matters, fundamentally, the deeper issue, the heart of the matter

Ceremony that promises a deeper truth, followed by an ordinary point.

Before: The real question is whether teams can adapt. At its core, what really matters is organizational readiness.

After: The question is whether teams can adapt. That mostly depends on whether the organization is ready to change its habits.

### 28. Signposting

Phrases to watch: let's dive in, let's explore, let's break this down, here's what you need to know, now let's look at, without further ado

Announcing the next move instead of making it.

Before: Let's dive into how caching works in Next.js. Here's what you need to know.

After: Next.js caches data at multiple layers, including request memoization, the data cache, and the router cache.

### 29. Fragmented headers

A heading, then a one-line paragraph restating the heading, then the actual content.

Before:

> ## Performance
>
> Speed matters.
>
> When users hit a slow page, they leave.

After:

> ## Performance
>
> When users hit a slow page, they leave.

## Worked example

A draft carrying most of the catalogue at once, then the three passes.

Original:

> Great question! Here is an essay on this topic. I hope this helps!
>
> AI-assisted coding serves as an enduring testament to the transformative potential of large language models, marking a pivotal moment in the evolution of software development. In today's rapidly evolving technological landscape, these groundbreaking tools—nestled at the intersection of research and practice—are reshaping how engineers ideate, iterate, and deliver, underscoring their vital role in modern workflows.
>
> At its core, the value proposition is clear: streamlining processes, enhancing collaboration, and fostering alignment. It's not just about autocomplete; it's about unlocking creativity at scale, ensuring that organizations can remain agile while delivering seamless, intuitive, and powerful experiences to users. The tool serves as a catalyst. The assistant functions as a partner. The system stands as a foundation for innovation.
>
> Industry observers have noted that adoption has accelerated from hobbyist experiments to enterprise-wide rollouts, from solo developers to cross-functional teams. The technology has been featured in The New York Times, Wired, and The Verge. Additionally, the ability to generate documentation, tests, and refactors showcases how AI can contribute to better outcomes, highlighting the intricate interplay between automation and human judgment.
>
> - 💡 **Speed:** Code generation is significantly faster, reducing friction and empowering developers.
> - 🚀 **Quality:** Output quality has been enhanced through improved training, contributing to higher standards.
> - ✅ **Adoption:** Usage continues to grow, reflecting broader industry trends.
>
> While specific details are limited based on available information, it could potentially be argued that these tools might have some positive effect. Despite challenges typical of emerging technologies—including hallucinations, bias, and accountability—the ecosystem continues to thrive. In order to fully realize this potential, teams must align with best practices.
>
> In conclusion, the future looks bright. Exciting times lie ahead as we continue this journey toward excellence. Let me know if you’d like me to expand on any section!

Draft rewrite:

> AI coding assistants speed up some tasks. The tools are good at boilerplate: config files, test scaffolding, repetitive refactors. They are bad at knowing when they are wrong. I have accepted suggestions that compiled, passed lint, and still did the wrong thing because I stopped paying attention.
>
> The productivity claims are hard to verify. Acceptance is not correctness, and correctness is not value. Teams I have talked to split roughly two ways: some use it like autocomplete for chores and review every line, others turn it off after it keeps suggesting patterns from a library they abandoned.
>
> None of this means the tools are useless. It means they are tools. They do not replace judgment, and they do not remove the need for tests. If you do not have tests, you cannot tell whether the suggestion is right.

What makes the below so obviously AI generated?

- The rhythm is still too tidy: clean contrasts, evenly paced paragraphs, every one landing on a neat closing line.
- "Teams I have talked to split roughly two ways" is a made-up specific. Either it happened or it should go.
- The closer leans slogan-y rather than sounding like a person talking.

Now make it not obviously AI generated.

> AI coding assistants can make you faster at the boring parts. Not everything. Definitely not architecture.
>
> They're great at boilerplate: config files, test scaffolding, repetitive refactors. They're also great at sounding right while being wrong. I've accepted suggestions that compiled, passed lint, and still missed the point, because I stopped paying attention.
>
> The productivity metrics are slippery. Acceptance isn't correctness, and correctness isn't value. And if you don't have tests, you're basically guessing about all of it.
