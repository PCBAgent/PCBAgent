def pytest_addoption(parser):
    parser.addoption(
        "--design",
        action="store",
        default=None,
        help="Design directory to verify. /design passes this. Without it, design tests skip.",
    )
