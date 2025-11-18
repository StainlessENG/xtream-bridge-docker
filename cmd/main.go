package main

import (
    "log"

    "iptv-proxy/internal"
)

func main() {
    err := internal.StartServer()
    if err != nil {
        log.Fatal(err)
    }
}
