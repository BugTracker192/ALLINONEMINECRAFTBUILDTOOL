def test_worker_package_imports() -> None:
    from mbi_worker.app import celery_app

    assert celery_app.main == "mbi"
