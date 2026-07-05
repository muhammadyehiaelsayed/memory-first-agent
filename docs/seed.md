# Redis Vector Search

Redis vector search stores numeric vector embeddings alongside regular fields in Redis
data structures and finds the entries whose vectors are nearest to a query vector. An
application converts text into an embedding with a model such as OpenAI's
text-embedding-3-small, stores it in a hash or JSON document, and declares a vector field
in a search index. At query time the application embeds the user's question the same way
and asks Redis for the k nearest neighbours.

## Index algorithms

Redis supports two main vector index algorithms. FLAT performs an exact brute-force scan
over every stored vector, which is deterministic and precise - the right choice while the
data set is small, in the hundreds or thousands of vectors. HNSW (Hierarchical Navigable
Small World) builds a layered graph for approximate nearest-neighbour search that scales
to millions of vectors while trading a little accuracy for large speed gains.

## Distance metrics

The COSINE metric measures the angle between two vectors and is the standard choice for
text embeddings. Redis returns a cosine distance, where distance equals one minus the
cosine similarity; a smaller distance means the vectors are more alike. Because OpenAI
embeddings are L2-normalized, converting the returned distance back to a similarity score
is an exact subtraction, which makes threshold-based routing decisions reproducible.

## Why it matters for agents

A memory-first agent embeds each incoming question, searches its Redis vector index
before touching the web, and answers directly from stored content when the best match
clears a similarity threshold. This makes repeated questions fast, cheap, and grounded in
sources the agent has already vetted and stored.
