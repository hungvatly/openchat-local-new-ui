import os
import json
from typing import List, Dict

try:
    import networkx as nx
except ImportError:
    nx = None

GRAPH_FILE = "data/knowledge_graph.json"

class GraphRAG:
    def __init__(self):
        self.graph = nx.DiGraph() if nx else None
        self._load_graph()

    def _load_graph(self):
        if not self.graph: return
        if os.path.exists(GRAPH_FILE):
            try:
                with open(GRAPH_FILE, 'r') as f:
                    data = json.load(f)
                    self.graph = nx.node_link_graph(data)
            except Exception:
                pass

    def _save_graph(self):
        if not self.graph: return
        os.makedirs(os.path.dirname(GRAPH_FILE), exist_ok=True)
        try:
            data = nx.node_link_data(self.graph)
            with open(GRAPH_FILE, 'w') as f:
                json.dump(data, f)
        except Exception:
            pass

    def add_relationship(self, source: str, target: str, relationship: str, document_id: str):
        if not self.graph: return
        self.graph.add_node(source)
        self.graph.add_node(target)
        self.graph.add_edge(source, target, relation=relationship, doc_id=document_id)
        self._save_graph()

    def build_related_context(self, query: str, max_depth: int = 1) -> str:
        """
        Naive approach: look for exact matches of nodes in the query text 
        and return their one-hop relationships to enrich the RAG prompt.
        """
        if not self.graph: return ""
        matched_nodes = []
        for node in self.graph.nodes():
            if str(node).lower() in query.lower():
                matched_nodes.append(node)
                
        if not matched_nodes:
            return ""

        context_lines = ["[GraphRAG Relationships:]"]
        visited = set()
        for node in matched_nodes[:5]:
            neighbors = list(self.graph.successors(node))
            for n in neighbors:
                edge_data = self.graph.get_edge_data(node, n)
                relation = edge_data.get('relation', 'is related to')
                fact = f"{node} --[{relation}]--> {n}"
                if fact not in visited:
                    context_lines.append(f"  - {fact}")
                    visited.add(fact)

        if len(context_lines) > 1:
            return "\n".join(context_lines)
        return ""

graph_rag = GraphRAG()
