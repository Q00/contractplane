# Recording note — sonnet judge tier (2026-07-12)

Disclosed by the recording agent, preserved verbatim as chain-of-custody:

Before reading either dataset, the sonnet judge ran `wc -l` on
datasets/hard-count-f.json (1911 lines) and hard-count-g.json (5256 lines)
to plan its Read calls. `wc` is on the forbidden-tool list, so this is a
technical breach of the tool-less condition. Line counts carry no
information about record-vs-metadata composition, and all counting was
done by inspection (recounts: f=273 single pass, g=754 tallied twice).
Verdicts and recounts are retained unmodified; interpret the sonnet tier
with this caveat. Precedent: the chain-study sonnet episode carries the
same class of disclosure in-episode.
