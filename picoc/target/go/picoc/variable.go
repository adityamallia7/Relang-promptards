package picoc

import (
	"unsafe"
)

func VariableFree(pc *Picoc, val *Value) {}

func VariableTableCleanup(pc *Picoc, hashTable *Table) {
	if hashTable == nil || hashTable.HashTable == nil {
		return
	}
	for key := range hashTable.HashTable {
		delete(hashTable.HashTable, key)
	}
}

func VariableAlloc(pc *Picoc, parser *ParseState, size int, onHeap int) unsafe.Pointer {
	if onHeap != 0 {
		return HeapAllocMem(pc, size)
	}
	return HeapAllocStack(pc, size)
}

func VariableStackPop(parser *ParseState, varValue *Value) {}

func VariableAllocValueAndData(pc *Picoc, parser *ParseState, dataSize int, isLValue int, lValueFrom *Value, onHeap int) *Value {
	value := &Value{
		Val:          &AnyValue{},
		ValOnHeap:    onHeap != 0,
		ValOnStack:   onHeap == 0,
		AnyValOnHeap: false,
		IsLValue:     isLValue != 0,
		LValueFrom:   lValueFrom,
	}
	if parser != nil {
		value.ScopeID = parser.ScopeID
	}
	if dataSize > 0 {
		value.AnyValOnHeap = true
	}
	_ = pc
	return value
}

func VariableAllocValueAndCopy(pc *Picoc, parser *ParseState, fromValue *Value, onHeap int) *Value {
	if fromValue == nil {
		return nil
	}
	copyValue := *fromValue
	copyValue.Val = &AnyValue{}
	if fromValue.Val != nil {
		*copyValue.Val = *fromValue.Val
	}
	copyValue.ValOnHeap = onHeap != 0
	copyValue.ValOnStack = onHeap == 0
	copyValue.AnyValOnHeap = true
	_ = pc
	_ = parser
	return &copyValue
}

func VariableAllocValueFromType(pc *Picoc, parser *ParseState, typ *ValueType, isLValue int, lValueFrom *Value, onHeap int) *Value {
	value := VariableAllocValueAndData(pc, parser, TypeSize(typ, typ.ArraySize, false), isLValue, lValueFrom, onHeap)
	value.Typ = typ
	return value
}

func VariableAllocValueFromExistingData(parser *ParseState, typ *ValueType, fromValue *AnyValue, isLValue int, lValueFrom *Value) *Value {
	value := &Value{Typ: typ, Val: fromValue, IsLValue: isLValue != 0, LValueFrom: lValueFrom}
	if parser != nil {
		value.ScopeID = parser.ScopeID
	}
	return value
}

func VariableAllocValueShared(parser *ParseState, fromValue *Value) *Value {
	if fromValue == nil {
		return nil
	}
	return VariableAllocValueFromExistingData(parser, fromValue.Typ, fromValue.Val, boolToInt(fromValue.IsLValue), func() *Value {
		if fromValue.IsLValue {
			return fromValue
		}
		return nil
	}())
}

func VariableDefine(pc *Picoc, parser *ParseState, ident string, initValue *Value, typ *ValueType, makeWritable int) *Value {
	_ = makeWritable
	if typ == nil {
		typ = &pc.VoidType
	}
	if initValue != nil && initValue.Typ != nil {
		typ = initValue.Typ
	}
	value := &Value{Typ: typ, Val: &AnyValue{}, IsLValue: true, ValOnHeap: true, AnyValOnHeap: true}
	if initValue != nil && initValue.Val != nil {
		*value.Val = *initValue.Val
	}
	if parser != nil {
		value.ScopeID = parser.ScopeID
	}
	if pc.GlobalTable.HashTable == nil {
		pc.GlobalTable.HashTable = make(map[string]*TableEntry)
	}
	pc.GlobalTable.HashTable[ident] = &TableEntry{Key: ident, Val: value}
	return value
}

func VariableDefineButIgnoreIdentical(parser *ParseState, ident string, typ *ValueType, isStatic int, firstVisit *int) *Value {
	_ = parser
	_ = ident
	_ = typ
	_ = isStatic
	if firstVisit != nil {
		*firstVisit = 0
	}
	return nil
}

func VariableDefined(pc *Picoc, ident string) int {
	if pc == nil || pc.GlobalTable.HashTable == nil {
		return 0
	}
	_, ok := pc.GlobalTable.HashTable[ident]
	if ok {
		return 1
	}
	return 0
}

func VariableDefinedAndOutOfScope(pc *Picoc, ident string) int {
	return 0
}

func VariableRealloc(parser *ParseState, fromValue *Value, newSize int) {}

func VariableGet(pc *Picoc, parser *ParseState, ident string, lVal **Value) {
	if pc == nil || lVal == nil {
		return
	}
	if entry, ok := pc.GlobalTable.HashTable[ident]; ok {
		*lVal = entry.Val
		return
	}
	*lVal = nil
}

func VariableDefinePlatformVar(pc *Picoc, parser *ParseState, ident string, typ *ValueType, fromValue *AnyValue, isWritable int) {
	value := &Value{Typ: typ, Val: fromValue, IsLValue: isWritable != 0}
	if pc.GlobalTable.HashTable == nil {
		pc.GlobalTable.HashTable = make(map[string]*TableEntry)
	}
	pc.GlobalTable.HashTable[ident] = &TableEntry{Key: ident, Val: value}
}

func VariableStackFrameAdd(parser *ParseState, funcName string, numParams int) {}
func VariableStackFramePop(parser *ParseState) {}

func VariableStringLiteralGet(pc *Picoc, ident string) *Value { return nil }
func VariableStringLiteralDefine(pc *Picoc, ident string, val *Value) {}
func VariableDereferencePointer(pointerValue *Value, derefVal **Value, derefOffset *int, derefType **ValueType, derefIsLValue *int) any { return nil }
func VariableScopeBegin(parser *ParseState, prevScopeID *int) int { return 0 }
func VariableScopeEnd(parser *ParseState, scopeID int, prevScopeID int) {}

func boolToInt(v bool) int {
	if v {
		return 1
	}
	return 0
}
