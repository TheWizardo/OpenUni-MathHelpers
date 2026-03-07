from dataclasses import dataclass
from typing import Dict, List
from collections import defaultdict
import tkinter as tk
from tkinter import simpledialog, messagebox
import networkx as nx
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import math
import random
import sys

NODE_SIZE = 1600

def point_radius_to_data_units(point_area, dpi=100, axis_size=6.0):
    pixel_area = point_area * (dpi / 72.0)**2
    radius_px = math.sqrt(pixel_area / math.pi)
    data_range_px = dpi * axis_size
    return radius_px / data_range_px

INTERACTION_RADIUS_SQUARED = point_radius_to_data_units(NODE_SIZE)**2

@dataclass
class Node:
    id: str
    x: float
    y: float
    label: str = None
    degree: int = 0

    @property
    def pos(self):
        return (self.x, self.y)

@dataclass
class Edge:
    src_node: str
    dst_node: str

class Graph:
    def __init__(self, directed=False):
        self.isDirected = directed
        self.nodes: Dict[str, Node] = {}
        self.edges: List[Edge] = []

    def add_node(self, node: Node):
        self.nodes[node.id] = node

    def add_edge(self, edge: Edge):
        self.edges.append(edge)
        self.recalculate_degrees()

    def remove_node(self, node_id: str):
        if node_id in self.nodes:
            del self.nodes[node_id]
        self.edges = [e for e in self.edges if e.src_node != node_id and e.dst_node != node_id]
        self.recalculate_degrees()

    def remove_edge(self, edge: Edge):
        if edge in self.edges:
            self.edges.remove(edge)
        self.recalculate_degrees()

    def recalculate_degrees(self):
        for node in self.nodes.values():
            node.degree = 0
        for e in self.edges:
            if e.src_node in self.nodes:
                self.nodes[e.src_node].degree += 1
            if e.dst_node in self.nodes and e.dst_node != e.src_node:
                self.nodes[e.dst_node].degree += 1

    @property
    def isEulerian(self):
        if not self.nodes:
            return False
        G = nx.MultiDiGraph() if self.isDirected else nx.MultiGraph()
        G.add_nodes_from(self.nodes.keys())
        G.add_edges_from((e.src_node, e.dst_node) for e in self.edges)
        return nx.is_eulerian(G)

    @property
    def isHamiltonian(self):
        return len(self.nodes) >= 3 and all(n.degree >= 2 for n in self.nodes.values())

class GraphApp:
    def __init__(self, root):
        self.root = root
        self.root.title("OOP Graph Editor")
        self.root.protocol("WM_DELETE_WINDOW", self.on_exit)

        self.directed = tk.BooleanVar()
        self.show_degree = tk.BooleanVar()
        self.graph = Graph()

        self.node_count = 0
        self.selected_node = None
        self.dragging = False
        self.adding_edge = False
        self.edge_source = None
        self.edge_preview_pos = None

        self.fig, self.ax = plt.subplots(figsize=(6, 6))
        self.canvas = FigureCanvasTkAgg(self.fig, master=root)
        self.canvas.get_tk_widget().pack()

        self.canvas.mpl_connect("button_press_event", self.on_press)
        self.canvas.mpl_connect("button_release_event", self.on_release)
        self.canvas.mpl_connect("motion_notify_event", self.on_motion)
        self.canvas.mpl_connect("button_press_event", self.on_right_click)

        self.status_label = tk.Label(root, text="Status", font=("Arial", 12))
        self.status_label.pack()
        self.properties_label = tk.Label(root, text="Properties", font=("Arial", 12))
        self.properties_label.pack()

        frame = tk.Frame(root)
        frame.pack()
        tk.Button(frame, text="Add Node", command=self.add_node).pack(side=tk.LEFT)
        self.edge_btn = tk.Button(frame, text="Add Edge", command=self.toggle_edge_mode)
        self.edge_btn.pack(side=tk.LEFT)
        tk.Button(frame, text="Clear", command=self.clear).pack(side=tk.LEFT)
        tk.Checkbutton(frame, text="Directed", variable=self.directed, command=self.toggle_directed).pack(side=tk.LEFT)
        tk.Checkbutton(frame, text="Show Degree", variable=self.show_degree, command=self.draw).pack(side=tk.LEFT)

        self.draw()

    def on_exit(self):
        self.root.destroy()
        sys.exit()

    def toggle_directed(self):
        self.graph.isDirected = self.directed.get()
        self.draw()

    def toggle_edge_mode(self):
        self.adding_edge = not self.adding_edge
        self.edge_source = None
        self.edge_preview_pos = None
        self.edge_btn.config(text="Cancel" if self.adding_edge else "Add Edge")
        self.draw()

    def add_node(self):
        self.node_count += 1
        node_id = str(self.node_count)

        for _ in range(100):
            x, y = random.uniform(0.1, 0.9), random.uniform(0.1, 0.9)
            if all((x - n.x)**2 + (y - n.y)**2 > INTERACTION_RADIUS_SQUARED for n in self.graph.nodes.values()):
                break
        else:
            x, y = 0.5, 0.5

        new_node = Node(id=node_id, x=x, y=y, label=node_id)
        self.graph.add_node(new_node)
        self.draw()

    def clear(self):
        self.graph = Graph(directed=self.directed.get())
        self.node_count = 0
        self.edge_btn.config(text="Add Edge")
        self.draw()

    def on_press(self, event):
        if not event.inaxes:
            return
        for node in self.graph.nodes.values():
            if (event.xdata - node.x)**2 + (event.ydata - node.y)**2 < INTERACTION_RADIUS_SQUARED:
                if event.dblclick:
                    self.edit_label(node)
                    return
                if self.adding_edge:
                    if self.edge_source is None:
                        self.edge_source = node.id
                    elif self.edge_source != node.id:
                        self.graph.add_edge(Edge(src_node=self.edge_source, dst_node=node.id))
                        self.edge_source = None
                        self.edge_preview_pos = None
                        self.adding_edge = False
                        self.edge_btn.config(text="Add Edge")
                        self.draw()
                    return
                else:
                    self.selected_node = node.id
                    self.dragging = True
                    return

    def on_right_click(self, event):
        if not event.inaxes or event.button != 3:
            return
        for node in list(self.graph.nodes.values()):
            if (event.xdata - node.x)**2 + (event.ydata - node.y)**2 < INTERACTION_RADIUS_SQUARED:
                if messagebox.askyesno("Delete Node", f"Delete node {self.graph.nodes[node.id].label}?"):
                    self.graph.remove_node(node.id)
                    self.draw()
                return
        for edge in list(self.graph.edges):
            if edge.src_node not in self.graph.nodes or edge.dst_node not in self.graph.nodes:
                continue
            x0, y0 = self.graph.nodes[edge.src_node].pos
            x1, y1 = self.graph.nodes[edge.dst_node].pos
            mx, my = (x0 + x1) / 2, (y0 + y1) / 2
            if (event.xdata - mx)**2 + (event.ydata - my)**2 < INTERACTION_RADIUS_SQUARED:
                if messagebox.askyesno("Delete Edge", f"Delete edge {self.graph.nodes[edge.src_node].label} → {self.graph.nodes[edge.dst_node].label}?"):
                    self.graph.remove_edge(edge)
                    self.draw()
                return

    def on_motion(self, event):
        if not event.inaxes:
            return
        if self.dragging and self.selected_node:
            self.graph.nodes[self.selected_node].x = event.xdata
            self.graph.nodes[self.selected_node].y = event.ydata
            self.draw()
        elif self.adding_edge and self.edge_source:
            self.edge_preview_pos = (event.xdata, event.ydata)
            self.draw()

    def on_release(self, event):
        self.dragging = False
        self.selected_node = None

    def edit_label(self, node):
        new_label = simpledialog.askstring("Edit Label", f"Label for node {node.id}:", initialvalue=node.label)
        if new_label:
            node.label = new_label
            self.draw()

    def draw(self):
        self.ax.clear()
        directed = self.graph.isDirected

        edge_groups = defaultdict(list)
        for edge in self.graph.edges:
            key = (edge.src_node, edge.dst_node) if directed else tuple(sorted([edge.src_node, edge.dst_node]))
            edge_groups[key].append(edge)

        for group in edge_groups.values():
            n = len(group)
            for i, edge in enumerate(group):
                if edge.src_node not in self.graph.nodes or edge.dst_node not in self.graph.nodes:
                    continue
                src = self.graph.nodes[edge.src_node]
                dst = self.graph.nodes[edge.dst_node]
                x0, y0 = src.pos
                x1, y1 = dst.pos
                offset = i - (n - 1) / 2
                rad = 0.25 * offset if n > 1 else 0
                self.ax.annotate("",
                                 xy=(x1, y1), xytext=(x0, y0),
                                 arrowprops=dict(arrowstyle='->' if directed else '-', lw=2, color='gray',
                                                 connectionstyle=f'arc3,rad={rad}'))

        if self.adding_edge and self.edge_source and self.edge_preview_pos:
            x0, y0 = self.graph.nodes[self.edge_source].pos
            x1, y1 = self.edge_preview_pos
            self.ax.annotate("",
                             xy=(x1, y1), xytext=(x0, y0),
                             arrowprops=dict(arrowstyle='->' if directed else '-', lw=2, color='red'))

        for node in self.graph.nodes.values():
            self.ax.plot(node.x, node.y, 'o', color='skyblue', markersize=math.sqrt(NODE_SIZE)/2)
            label = str(node.degree) if self.show_degree.get() else node.label
            color = 'blue' if self.show_degree.get() else 'black'
            self.ax.text(node.x, node.y, label, fontsize=10, ha='center', va='center', color=color)

        self.canvas.draw()
        self.update_status()
        
    def compute_prufer_sequence(self) -> str:
        if len(self.graph.nodes) == 0:
            return []

        # Build a NetworkX graph from our custom Graph class
        G = nx.Graph()
        G.add_nodes_from(self.graph.nodes.keys())
        G.add_edges_from((edge.src_node, edge.dst_node) for edge in self.graph.edges)

        if not nx.is_tree(G):
            return "not a tree"
            # raise ValueError("Prufer sequence is only defined for trees (connected and acyclic graphs).")

        # Convert to int labels if necessary
        degree = dict(G.degree())
        prufer = []
        nodes = sorted(G.nodes(), key=lambda x: int(x))

        for _ in range(len(G.nodes) - 2):
            leaf = min([v for v in nodes if degree[v] == 1], key=lambda x: int(x))
            for neighbor in G.neighbors(leaf):
                if degree[neighbor] > 0:
                    prufer.append(self.graph.nodes[neighbor].label)
                    degree[neighbor] -= 1
                    break
            degree[leaf] -= 1

        return str(prufer)

    def update_status(self):
        status_text = f"|V|: {len(self.graph.nodes)} ; |E|: {len(self.graph.edges)}; Prufer: {self.compute_prufer_sequence()}"
        self.status_label.config(text=status_text)
        propeties_text = f"Eulerian: {'Yes' if self.graph.isEulerian else 'No'} | Hamiltonian: {'Yes' if self.graph.isHamiltonian else 'No'}"
        self.properties_label.config(text=propeties_text)

if __name__ == "__main__":
    root = tk.Tk()
    app = GraphApp(root)
    root.mainloop()