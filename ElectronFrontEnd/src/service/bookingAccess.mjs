export function resolveBookingAccess(data) {
    const countBookings = (obj) => {
        if (!obj || typeof obj !== 'object') return 0;
        if (Array.isArray(obj.partner_bookings)) return obj.partner_bookings.length;
        if (Array.isArray(obj.bookings)) return obj.bookings.length;
        if (typeof obj.booking_count === 'number') return obj.booking_count;
        return 0;
    };

    let bookingCount = Math.max(countBookings(data), countBookings(data?.data));
    if (bookingCount === 0 && (data?.has_booking || data?.data?.has_booking)) {
        bookingCount = 1;
    }

    return {
        bookingCount,
        hasSessionOne: bookingCount >= 1,
        hasAdvancedBooking: bookingCount >= 2,
        hasSessionThree: bookingCount >= 3,
    };
}
