"""Run five replay rooms and one live laptop-webcam room."""
import argparse


def main():
    parser = argparse.ArgumentParser(description="VinFall: 5 replay rooms + laptop webcam in room 106, with multi-person tracking")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=8000, type=int)
    args = parser.parse_args()
    import uvicorn
    from .server import create_app
    uvicorn.run(create_app(), host=args.host, port=args.port)


if __name__ == "__main__":
    main()
