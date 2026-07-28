package main

import (
	"os"

	"picocgo/picoc"
)

func main() {
	os.Exit(picoc.Main(os.Args[1:]))
}
