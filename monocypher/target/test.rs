fn f(a: &mut [i32;10], b: &[i32;10]) {} fn main() { let mut a = [0;10]; f(&mut a, &{a}); }
