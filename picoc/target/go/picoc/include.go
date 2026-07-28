package picoc

import "strings"

type includeRegistry struct {
	name   string
	setup  func(*Picoc)
	funcs  []LibraryFunction
	source string
}

var includeLibraries []*IncludeLibrary

func IncludeInit(pc *Picoc) {
	IncludeRegister(pc, "ctype.h", nil, StdCtypeFunctions, "")
	IncludeRegister(pc, "errno.h", StdErrnoSetupFunc, nil, "")
	IncludeRegister(pc, "math.h", MathSetupFunc, MathFunctions, "")
	IncludeRegister(pc, "stdbool.h", StdboolSetupFunc, nil, StdboolDefs)
	IncludeRegister(pc, "stdio.h", StdioSetupFunc, StdioFunctions, StdioDefs)
	IncludeRegister(pc, "stdlib.h", StdlibSetupFunc, StdlibFunctions, "")
	IncludeRegister(pc, "string.h", StringSetupFunc, StringFunctions, "")
	IncludeRegister(pc, "time.h", StdTimeSetupFunc, StdTimeFunctions, StdTimeDefs)
	IncludeRegister(pc, "unistd.h", UnistdSetupFunc, UnistdFunctions, UnistdDefs)
}

func IncludeCleanup(pc *Picoc) {
	includeLibraries = nil
}

func IncludeRegister(pc *Picoc, includeName string, setupFunction func(*Picoc), funcList []LibraryFunction, setupCSource string) {
	includeLibraries = append(includeLibraries, &IncludeLibrary{
		IncludeName:   TableStrRegister(pc, includeName),
		SetupFunction: setupFunction,
		FuncList:      funcList,
		SetupCSource:  setupCSource,
	})
	if pc != nil {
		pc.IncludeLibList = includeLibraries[0]
		for i := 0; i < len(includeLibraries)-1; i++ {
			includeLibraries[i].NextLib = includeLibraries[i+1]
		}
	}
}

func IncludeFile(pc *Picoc, filename string) {
	for _, lib := range includeLibraries {
		if strings.EqualFold(lib.IncludeName, filename) {
			if VariableDefined(pc, filename) == 0 {
				VariableDefine(pc, nil, filename, nil, &pc.VoidType, 0)
				if lib.SetupFunction != nil {
					lib.SetupFunction(pc)
				}
				if lib.SetupCSource != "" {
					PicocParse(pc, filename, lib.SetupCSource, len(lib.SetupCSource), true, true, false, false)
				}
				if len(lib.FuncList) > 0 {
					LibraryAdd(pc, lib.FuncList)
				}
			}
			return
		}
	}
	PicocPlatformScanFile(pc, filename)
}

func PicocIncludeAllSystemHeaders(pc *Picoc) {
	for _, lib := range includeLibraries {
		IncludeFile(pc, lib.IncludeName)
	}
}

