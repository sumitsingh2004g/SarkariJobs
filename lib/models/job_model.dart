class Job {
  final int? id;
  final String title;
  final String organization;
  final String totalVacancies;
  final DateTime? startDate;
  final DateTime lastDate;
  final String feeDetails;
  final String eligibility;
  final String officialApplyLink;

  Job({
    this.id,
    required this.title,
    required this.organization,
    required this.totalVacancies,
    this.startDate,
    required this.lastDate,
    required this.feeDetails,
    required this.eligibility,
    required this.officialApplyLink,
  });

  factory Job.fromJson(Map<String, dynamic> json) {
    DateTime parseDateToIso(String? dateStr) {
      if (dateStr == null || dateStr.isEmpty) {
        return DateTime.now().add(Duration(days: 365));
      }
      
      if (dateStr.contains('/')) {
        final parts = dateStr.split('/');
        if (parts.length == 3) {
          return DateTime(int.parse(parts[2]), int.parse(parts[1]), int.parse(parts[0]));
        }
      }
      
      if (dateStr.contains('-')) {
        final parts = dateStr.split('-');
        if (parts.length == 3 && parts[0].length == 4) {
          return DateTime.parse(dateStr);
        } else if (parts.length == 3) {
          return DateTime(int.parse(parts[2]), int.parse(parts[1]), int.parse(parts[0]));
        }
      }
      
      return DateTime.tryParse(dateStr) ?? DateTime.now().add(Duration(days: 365));
    }

    return Job(
      id: json['id'] as int?,
      title: json['title'] as String? ?? 'Unknown',
      organization: json['organization'] as String? ?? 'Other',
      totalVacancies: json['total_vacancies'] as String? ?? 'Not specified',
      startDate: json['start_date'] != null
          ? parseDateToIso(json['start_date'] as String?)
          : null,
      lastDate: parseDateToIso(json['last_date'] as String?),
      feeDetails: json['fee_details'] as String? ?? 'As per official notification',
      eligibility: json['eligibility'] as String? ?? 'As per official notification',
      officialApplyLink: json['official_apply_link'] as String? ?? '',
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'id': id,
      'title': title,
      'organization': organization,
      'total_vacancies': totalVacancies,
      'start_date': startDate?.toIso8601String().split('T')[0],
      'last_date': lastDate.toIso8601String().split('T')[0],
      'fee_details': feeDetails,
      'eligibility': eligibility,
      'official_apply_link': officialApplyLink,
    };
  }
}