with open("src/market/binance.py", "r") as f:
    text = f.read()
text = text.replace('url = f"{self.ws_url.replace(\\"/ws\\", \\"/stream?streams=\\")}{stream_name}"', 'url = f"{self.ws_url.replace(\'/ws\', \'/stream?streams=\')}{stream_name}"')
with open("src/market/binance.py", "w") as f:
    f.write(text)
