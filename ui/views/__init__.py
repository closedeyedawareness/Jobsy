"""Jobsy's pages, one module each. Split out of ui/app.py on 2026-09-03.

NOT named `pages`: Streamlit reserves a `pages/` directory next to the
entrypoint for its automatic multipage navigation. When these modules lived
there, Streamlit listed every one of them in the sidebar and served each at
its own URL -- reached WITHOUT ui/app.py running, so without the password
gate. tests/test_ui_structure.py keeps that from coming back.
"""
