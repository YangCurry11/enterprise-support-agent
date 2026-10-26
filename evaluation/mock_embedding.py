"""Lexical hashing MOCK: tests wiring, not semantic quality or real model tokens."""
from sklearn.feature_extraction.text import HashingVectorizer


class MockEmbedding:
    def __init__(self, dimensions=128):
        self.vectorizer = HashingVectorizer(analyzer="char", ngram_range=(1, 2),
            n_features=dimensions, alternate_sign=False, lowercase=False, norm="l2")
        self.invocations = 0

    def embed(self, texts, ledger):
        self.invocations += 1
        return self.vectorizer.transform(texts).toarray()
