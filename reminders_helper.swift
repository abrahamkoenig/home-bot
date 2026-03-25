#!/usr/bin/env swift
import EventKit
import Foundation

let store = EKEventStore()
let semaphore = DispatchSemaphore(value: 0)

// Request access
if #available(macOS 14.0, *) {
    store.requestFullAccessToReminders { granted, error in
        if !granted {
            print("ERROR: Reminders access denied")
            exit(1)
        }
        semaphore.signal()
    }
} else {
    store.requestAccess(to: .reminder) { granted, error in
        if !granted {
            print("ERROR: Reminders access denied")
            exit(1)
        }
        semaphore.signal()
    }
}
semaphore.wait()

let args = CommandLine.arguments
guard args.count >= 2 else {
    print("Usage: reminders_helper.swift <command> [args...]")
    print("Commands: list [listname], create <title> [due_date] [list], complete <name>, lists")
    exit(1)
}

let command = args[1]

switch command {
case "lists":
    let calendars = store.calendars(for: .reminder)
    for cal in calendars {
        print(cal.title)
    }

case "list":
    let listFilter = args.count > 2 ? args[2] : ""
    let calendars = store.calendars(for: .reminder)
    let targetCals = listFilter.isEmpty ? calendars : calendars.filter { $0.title == listFilter }

    let predicate = store.predicateForIncompleteReminders(withDueDateStarting: nil, ending: nil, calendars: targetCals.isEmpty ? nil : targetCals)

    var reminders: [EKReminder] = []
    let fetchSemaphore = DispatchSemaphore(value: 0)
    store.fetchReminders(matching: predicate) { result in
        reminders = result ?? []
        fetchSemaphore.signal()
    }
    fetchSemaphore.wait()

    if reminders.isEmpty {
        print("Keine offenen Erinnerungen.")
    } else {
        let formatter = DateFormatter()
        formatter.dateFormat = "yyyy-MM-dd"
        for r in reminders.sorted(by: {
            ($0.dueDateComponents?.date ?? Date.distantFuture) < ($1.dueDateComponents?.date ?? Date.distantFuture)
        }) {
            let listName = r.calendar.title
            var line = r.title ?? "?"
            if let dueComps = r.dueDateComponents, let dueDate = Calendar.current.date(from: dueComps) {
                line += " | fällig: \(formatter.string(from: dueDate))"
            }
            line += " [\(listName)]"
            print(line)
        }
    }

case "create":
    guard args.count >= 3 else {
        print("ERROR: Missing title")
        exit(1)
    }
    let title = args[2]
    let dueDateStr = args.count > 3 ? args[3] : ""
    let listName = args.count > 4 ? args[4] : ""

    let reminder = EKReminder(eventStore: store)
    reminder.title = title

    // Find target calendar
    if !listName.isEmpty {
        if let cal = store.calendars(for: .reminder).first(where: { $0.title == listName }) {
            reminder.calendar = cal
        } else {
            print("ERROR: Liste '\(listName)' nicht gefunden")
            exit(1)
        }
    } else {
        reminder.calendar = store.defaultCalendarForNewReminders()
    }

    // Set due date
    if !dueDateStr.isEmpty {
        let formatter = DateFormatter()
        formatter.dateFormat = "yyyy-MM-dd"
        if let date = formatter.date(from: dueDateStr) {
            var comps = Calendar.current.dateComponents([.year, .month, .day], from: date)
            comps.hour = 9
            comps.minute = 0
            reminder.dueDateComponents = comps
            reminder.addAlarm(EKAlarm(absoluteDate: Calendar.current.date(from: comps)!))
        }
    }

    do {
        try store.save(reminder, commit: true)
        var msg = "Erinnerung erstellt: \(title)"
        if !dueDateStr.isEmpty { msg += " (fällig: \(dueDateStr))" }
        if !listName.isEmpty { msg += " in Liste '\(listName)'" }
        print(msg)
    } catch {
        print("ERROR: \(error.localizedDescription)")
        exit(1)
    }

case "complete":
    guard args.count >= 3 else {
        print("ERROR: Missing name")
        exit(1)
    }
    let searchName = args[2].lowercased()

    let predicate = store.predicateForIncompleteReminders(withDueDateStarting: nil, ending: nil, calendars: nil)
    var reminders: [EKReminder] = []
    let fetchSemaphore = DispatchSemaphore(value: 0)
    store.fetchReminders(matching: predicate) { result in
        reminders = result ?? []
        fetchSemaphore.signal()
    }
    fetchSemaphore.wait()

    let matches = reminders.filter { ($0.title ?? "").lowercased().contains(searchName) }
    if matches.isEmpty {
        print("Keine passende Erinnerung gefunden.")
    } else {
        for r in matches {
            r.isCompleted = true
            do {
                try store.save(r, commit: true)
            } catch {
                print("ERROR: \(error.localizedDescription)")
                exit(1)
            }
        }
        print("Erinnerung '\(matches[0].title ?? searchName)' als erledigt markiert.")
    }

default:
    print("ERROR: Unknown command '\(command)'")
    exit(1)
}
