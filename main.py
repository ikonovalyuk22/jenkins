import json
import socket
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

from prometheus_client import (
    Counter,
    Gauge,
    generate_latest,
    CONTENT_TYPE_LATEST
)
import psutil

PORT = 5000

# ===== Prometheus metrics =====

REQUESTS_TOTAL = Counter(
    'app_requests_total',
    'Total HTTP requests'
)

CPU_USAGE = Gauge(
    'app_cpu_usage_percent',
    'CPU usage percent'
)

RAM_USAGE = Gauge(
    'app_ram_usage_percent',
    'RAM usage percent'
)

# ===== HTTP Handler =====

class ApiRequestHandler(BaseHTTPRequestHandler):

    def __init__(self, request, client_address, ref_req, api_ref):
        self.api = api_ref
        super().__init__(request, client_address, ref_req)

    def call_api(self, method, path, args):
        REQUESTS_TOTAL.inc()

        if path in api.routing[method]:
            try:
                result = api.routing[method][path](args)
                self.send_response(200)
                self.end_headers()
                self.wfile.write(json.dumps(result, indent=4).encode())
            except Exception as e:
                self.send_response(500, "Server Error")
                self.end_headers()
                self.wfile.write(json.dumps(
                    {"error": str(e)},
                    indent=4
                ).encode())
        else:
            self.send_response(404, "Not Found")
            self.end_headers()
            self.wfile.write(json.dumps(
                {"error": "not found"},
                indent=4
            ).encode())

    def do_GET(self):
        parsed_url = urlparse(self.path)
        path = parsed_url.path
        args = parse_qs(parsed_url.query)

        for k in args.keys():
            if len(args[k]) == 1:
                args[k] = args[k][0]

        # ---- healthcheck ----
        if path == "/health":
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"OK")
            return

        # ---- prometheus metrics ----
        if path == "/metrics":
            CPU_USAGE.set(psutil.cpu_percent())
            RAM_USAGE.set(psutil.virtual_memory().percent)

            self.send_response(200)
            self.send_header("Content-Type", CONTENT_TYPE_LATEST)
            self.end_headers()
            self.wfile.write(generate_latest())
            return

        self.call_api("GET", path, args)

    def do_POST(self):
        parsed_url = urlparse(self.path)
        path = parsed_url.path

        if self.headers.get("content-type") != "application/json":
            self.send_response(400)
            self.end_headers()
            self.wfile.write(json.dumps({
                "error": "posted data must be in json format"
            }, indent=4).encode())
        else:
            data_len = int(self.headers.get("content-length"))
            data = self.rfile.read(data_len).decode()
            self.call_api("POST", path, json.loads(data))


# ===== API Router =====

class API():
    def __init__(self):
        self.routing = {"GET": {}, "POST": {}}

    def get(self, path):
        def wrapper(fn):
            self.routing["GET"][path] = fn
        return wrapper

    def post(self, path):
        def wrapper(fn):
            self.routing["POST"][path] = fn
        return wrapper

    def __call__(self, request, client_address, ref_request):
        return ApiRequestHandler(
            request,
            client_address,
            ref_request,
            api_ref=self
        )


api = API()

# ===== Example data =====

example_data = {
    "items": [
        {"id": 1000, "name": "cat", "description": "cat is meowing"},
        {"id": 1001, "name": "dog", "description": "dog is barking"},
        {"id": 1002, "name": "bird", "description": "bird is singing"}
    ]
}

# ===== API endpoints =====

@api.get("/")
def index(_):
    return {
        "name": "Python REST API Example",
        "summary": "Simple REST API with pure Python",
        "version": "1.0.0",
        "hostname": socket.gethostname()
    }


@api.get("/list")
def list_items(_):
    return {
        "count": len(example_data["items"]),
        "items": example_data["items"]
    }


@api.get("/search")
def search(args):
    q = args.get("q")

    if q is None:
        return {"error": "q parameter required"}

    results = [
        item for item in example_data["items"]
        if q in item["name"]
    ]

    return {"count": len(results), "items": results}


@api.post("/add")
def add(args):
    last_id = example_data["items"][-1]["id"]
    name = args.get("name")
    description = args.get("description")

    if name is None or description is None:
        return {"error": "name and description are required"}

    item = {
        "id": last_id + 1,
        "name": name,
        "description": description
    }

    example_data["items"].append(item)
    return item


@api.post("/delete")
def delete(args):
    item_id = args.get("id")

    if item_id is None:
        return {"error": "id parameter required"}

    for item in example_data["items"]:
        if item["id"] == item_id:
            example_data["items"].remove(item)
            return {"deleted": item_id}

    return {"error": f"item not found with id {item_id}"}


# ===== Main =====

if __name__ == "__main__":
    print("Application started on host:", socket.gethostname())
    print(f"Listening on port {PORT}")

    httpd = HTTPServer(("", PORT), api)
    httpd.serve_forever()
