class DisjointSet:
    def __init__(self, size: int) -> None:
        self._parents = list(range(size))

    def find(self, item: int) -> int:
        root = item
        while self._parents[root] != root:
            root = self._parents[root]
        while self._parents[item] != root:
            self._parents[item], item = root, self._parents[item]
        return root

    def union(self, first: int, second: int) -> None:
        self._parents[self.find(first)] = self.find(second)

    def groups(self) -> list[list[int]]:
        grouped: dict[int, list[int]] = {}
        for item in range(len(self._parents)):
            grouped.setdefault(self.find(item), []).append(item)
        return list(grouped.values())
